Proyecto Final: EventFlow - Sistema Distribuido Resiliente

Asignatura: Sistemas Distribuidos

1. Descripción del Proyecto

EventFlow es una plataforma de venta y gestión de tickets diseñada con una arquitectura de microservicios radicalmente enfocada en la Alta Disponibilidad y Tolerancia a Fallos.

El objetivo principal de este proyecto es demostrar que el sistema puede continuar aceptando y procesando transacciones (Escrituras) y atendiendo consultas (Lecturas) incluso si la Base de Datos Principal (SPOF) está completamente detenida.

Arquitectura de Despliegue

La solución se basa en un patrón de mensajería asíncrona y caché que desacopla la aplicación principal del Punto Único de Fallo (SPOF).

Componente

Rol en la Resiliencia

Tecnología

Backend Principal

Distribuye tráfico y aplica la lógica de resiliencia.

FastAPI (Python) - 3 Nodos

Balanceador de Carga

Distribuye el tráfico y gestiona el health check de los 3 nodos.

NGINX

SPOF (BD Principal)

Almacenamiento crítico (Punto de Fallo intencional).

PostgreSQL

Caché

Sirve Lecturas rápidas y mantiene la disponibilidad cuando la BD falla.

Redis

Cola de Mensajes

Almacena y garantiza la durabilidad de las Escrituras cuando la BD falla.

RabbitMQ

MS 1: Notificaciones

Consumidor: Escribe en la BD y se recupera automáticamente.

Python Script (Resiliente)

MS 2: Análisis

API REST para consultas pesadas.

FastAPI (Python)

Monitoreo

Recolección de métricas de disponibilidad y latencia.

Prometheus & Grafana

2. Requisitos Previos

Asegúrese de tener instalado y ejecutándose:

Docker Desktop (con el motor Linux/WSL2 activo).

Docker Compose (Generalmente incluido en Docker Desktop).

Python 3 (para ejecutar el script de prueba E2E).

Librerías de Python: pip install requests

3. Despliegue del Sistema

El sistema se despliega utilizando un solo comando desde el directorio raíz (Distribuidos proyecto final/):

3.1. Arranque Inicial

Asegúrese de estar en la carpeta raíz que contiene el archivo docker-compose.yml.

Ejecute el comando para construir las imágenes y levantar todos los servicios:

docker-compose up --build -d


3.2. Endpoints y Monitoreo

Una vez que los 10 contenedores estén levantados:

Componente

Endpoint de Acceso

Descripción

GUI Principal

http://localhost/

Interfaz para la demostración visual.

Balanceador (NGINX)

http://localhost/health

Verifica la distribución de carga.

Gestión de Cola

http://localhost:15672

Interfaz de RabbitMQ (usuario/pass: guest/guest).

Prometheus

http://localhost:9090

Servidor de métricas.

Grafana

http://localhost:3000

Dashboards (user/pass: admin/admin).

4. ⚔️ Prueba de Tolerancia a Fallos (Requisito Crítico)

Esta prueba End-to-End (e2e_resilience_test.py) demuestra la capacidad del sistema para aceptar 5 transacciones mientras la Base de Datos está detenida y recuperar los datos automáticamente al restablecerse.

4.1. Ejecución del Test E2E

El script maneja los comandos de docker stop y docker start automáticamente.

Ejecute la prueba desde PowerShell (o Terminal):

python eventflow-distribuido/tests/e2e_resilience_test.py


4.2. Flujo de la Prueba y Verificación

El script confirmará el ÉXITO si cumple los siguientes pasos:

Detención: Detiene el contenedor postgres_spof.

Escritura Resiliente: Envía 5 peticiones POST a /purchase y verifica que la respuesta sea ACCEPTED_ASYNC (el sistema encola, no falla).

Recuperación: Restaura el contenedor postgres_spof.

Verificación Final: Espera hasta que los logs del consumidor (ms-notificaciones) muestren "CONSUMER SUCCESS" 5 veces.

Si el test finaliza con el mensaje: --- TEST E2E DE RESILIENCIA FINALIZADO CON ÉXITO ---, se cumple el requisito de integración/E2E.

5. Pruebas Unitarias (CI/CD Mínimo)

El pipeline de CI/CD ejecutará un total de 10 pruebas, cubriendo la lógica de negocio y el flujo E2E:

Servicio

Test #

Lógica Cubierta

App Principal

3

Cálculo de precios, validación de cantidad de tickets, validación de formato JSON.

MS Notificaciones

2

Construcción del cuerpo del email, verificación del parser de la cola.

MS Análisis

2

Cálculo de ingresos totales, manejo de datos nulos en métricas.

Común

2

Funciones de hashing de contraseñas, función de verificación de Redis UP/DOWN.

Integración / E2E

1

Flujo completo de Compra Asíncrona bajo Fallo de BD.

6. Video de Evidencia de Tolerancia a Fallos

Para el requisito de video de evidencia, se demostrará el siguiente escenario utilizando la GUI (index.html):

BD UP: Se realiza una Lectura y una Escritura.

Simulación de Fallo: Se detiene el contenedor postgres_spof manualmente.

BD DOWN: Se realizan 5 Escrituras. Se verifica en la GUI que la respuesta es ÉXITO ASÍNCRONO.

Monitoreo: Se muestra en Grafana que el target de PostgreSQL está DOWN mientras los nodos de la App están UP.

Recuperación: Se inicia el contenedor postgres_spof. Se muestra en los logs del consumidor cómo las 5 transacciones se procesan.
