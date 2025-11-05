import os
import redis
import psycopg2
from fastapi import FastAPI, HTTPException
import uvicorn
import json
import time 
import pika 

# --- Configuración del Entorno ---
NODE_ID = os.environ.get("NODE_ID", "UNKNOWN")
DB_HOST = os.environ.get("DB_HOST")
REDIS_HOST = os.environ.get("REDIS_HOST")
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST")

app = FastAPI(
    title=f"EventFlow Node {NODE_ID}",
    description="Backend para gestión de eventos con resiliencia de lectura/escritura.",
    version="1.0.0"
)

# --- CLIENTES DE CONEXIÓN ---
REDIS_CLIENT = None
try:
    REDIS_CLIENT = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    REDIS_CLIENT.ping()
    print("INFO: Conexión exitosa a Redis.")
except Exception as e:
    print(f"ERROR: Falló la conexión inicial a Redis: {e}.")
    REDIS_CLIENT = None

def get_db_connection():
    # ... (El código de esta función es correcto, no necesita cambios) ...
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database="eventflow_db",
            user="user",
            password="password",
            connect_timeout=1
        )
        return conn
    except Exception as e:
        return None

# --- FUNCIÓN CLAVE: Conexión Lazy a RabbitMQ con Retries ---
def get_rabbitmq_channel(max_retries=5, delay=1):
    """
    Intenta reconectar a RabbitMQ con retries.
    Esto hace que la publicación sea resiliente a fallos transitorios de conexión.
    """
    for attempt in range(max_retries):
        try:
            # CLAVE: Añadir timeouts para que la conexión falle rápido si RabbitMQ no está disponible.
            params = pika.ConnectionParameters(
                host=RABBITMQ_HOST, port=5672,
                blocked_connection_timeout=2 # Timeout para cada intento de conexión
            )
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue='transaction_queue', durable=True)
            return channel
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"WARNING: Falló la conexión a RabbitMQ (Intento {attempt + 1}/{max_retries}). Reintentando en {delay}s.")
                time.sleep(delay)
            else:
                print(f"CRITICAL ERROR: Falló la conexión a RabbitMQ después de {max_retries} intentos: {e}")
    return None

# Función para publicar en la cola
def publish_to_queue(message_body: dict):
    """Publica el mensaje en la cola de transacciones."""
    # Intentamos obtener el canal justo antes de publicar (con retries)
    channel = get_rabbitmq_channel()
    if channel is None:
        # Esta excepción será capturada por el bloque try/except del endpoint /purchase
        raise Exception("RabbitMQ channel is not available for publishing.")

    channel.basic_publish(
        exchange='',
        routing_key='transaction_queue',
        body=json.dumps(message_body),
        properties=pika.BasicProperties(
            delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
        )
    )
    # Es crucial cerrar la conexión después de enviar para no saturar los recursos
    channel.connection.close()


# --- Endpoints Básicos y Health ---

@app.get("/")
def read_root():
    return {
        "status": "up", 
        "message": f"Hello from Node {NODE_ID} (Port 8000)",
        "environment": {"db": DB_HOST, "cache": REDIS_HOST, "queue": RABBITMQ_HOST}
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- Lógica de Lectura Resiliente (Cache-Aside) ---
# (Dejar todo el código de /events/{event_id} sin cambios)
@app.get("/events/{event_id}")
def get_event_details(event_id: int):
    # ... (código de la función get_event_details sin cambios) ...
    """
    Implementa la estrategia Cache-Aside. 
    Garantiza disponibilidad de lectura si la BD falla (usando datos de Redis).
    """
    cache_key = f"event:{event_id}"

    # 1. Intento de Lectura: Cache First (ALTA DISPONIBILIDAD)
    if REDIS_CLIENT:
        data = REDIS_CLIENT.get(cache_key)
        if data:
            # Deserializa la cadena JSON almacenada en Redis
            return {"source": "cache", "event": json.loads(data)}
    
    # --- BD Fallback: Si no está en caché o Redis está caído ---

    conn = get_db_connection()
    if conn:
        try:
            # Simulamos la obtención de datos de evento (Ejemplo simple)
            # Nota: Para esta demo, solo se necesita el evento 999
            if event_id == 999:
                 result = [999, 'Conferencia Sistemas Dist.', 'Resiliencia demo data']
            else:
                 result = None # No encontrado

            if result:
                # 2. Cache-Aside: Actualiza el caché después de leer de la BD
                event_data = {"id": event_id, "name": result[1], "description": result[2]}
                if REDIS_CLIENT:
                    # Serializa a JSON antes de guardar en Redis
                    REDIS_CLIENT.set(cache_key, json.dumps(event_data), ex=300) 
                
                return {"source": "database", "event": event_data}
            else:
                # La BD está up, pero el evento no existe
                raise HTTPException(status_code=404, detail="Event not found in Database.")
        
        except Exception as e:
            # Error durante la Query, no durante la conexión.
            print(f"DB Query Error: {e}")
            raise HTTPException(status_code=503, detail="Database error during query.")

    # 3. Fallo Total: Si la BD está caída Y hubo un Cache Miss.
    raise HTTPException(status_code=503, detail="System unavailable: DB is down and data not found in cache.")


# --- Lógica de Escritura Resiliente (CLAVE) ---

@app.post("/purchase") 
def create_purchase(user_id: int, event_id: int, quantity: int):
    """
    Endpoint de Compra de Tickets. Usa la estrategia de ESCRITURA ASÍNCRONA.
    """
    transaction_data = {
        "user_id": user_id,
        "event_id": event_id,
        "quantity": quantity,
        "timestamp": time.time(),
        "transaction_id": os.urandom(8).hex() 
    }

    try:
        # Publica la transacción en la cola de mensajes
        publish_to_queue(transaction_data)

        # La respuesta al usuario es inmediata y positiva (aceptada para procesamiento)
        return {
            "status": "ACCEPTED_ASYNC",
            "message": "Transaction accepted and queued for processing.",
            "transaction_id": transaction_data["transaction_id"]
        }

    except Exception as e:
        # Si RabbitMQ también falla, el sistema debe responder con un error crítico (503)
        print(f"CRITICAL ERROR: Failed to publish to RabbitMQ: {e}")
        # El 503 es la respuesta correcta si no podemos ni siquiera encolar la transacción.
        raise HTTPException(
            status_code=503,
            detail="System critical failure: Cannot queue transaction. Try again later."
        )

# --- Inicialización simulada de datos (Solo para la demo) ---
@app.on_event("startup")
def startup_event():
    # ... (código de inicialización sin cambios) ...
    if REDIS_CLIENT:
        try:
            # Usaremos el ID 999 para la demostración
            demo_data = {"id": 999, "name": "Conferencia Sistemas Dist.", "description": "Resiliencia demo data"}
            REDIS_CLIENT.set(f"event:999", json.dumps(demo_data), ex=300)
            print("INFO: Evento 999 precargado en Redis.")
        except Exception as e:
            print(f"WARNING: No se pudo precargar Redis: {e}")
