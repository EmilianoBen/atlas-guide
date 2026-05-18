# Atlas Guide

Web app para buscar vuelos, hoteles y opciones de Airbnb desde un solo lugar. La idea surgió como proyecto personal para practicar integración de APIs externas y despliegue con Docker. Tiene un chatbot integrado que sirve como asistente de viaje.

---

## Tecnologías

- Python / FastAPI / Uvicorn
- JavaScript vanilla, HTML, CSS
- Docker y Docker Compose
- ngrok (para exponer la app a internet sin deploy)
- APIs: Duffel (vuelos y hoteles), Geoapify, RapidAPI

---

## Instalación

Necesitas tener Docker Desktop instalado.

1. Clona el repositorio:

```bash
git clone https://github.com/EmilianoBen/atlas-guide.git
cd atlas-guide
```

2. Crea tu archivo de entorno a partir del ejemplo:

```bash
cp .env.example .env
```

3. Abre `.env` y agrega tus claves de API. El archivo `.env.example` tiene los nombres de todas las variables que necesitas.

4. Levanta la app:

```bash
docker compose up --build -d
```

5. Abre el navegador en `http://localhost:8000`.

---

## Uso

La interfaz tiene tres pestañas principales: Vuelos, Hoteles y Airbnb.

- **Vuelos**: ingresa los códigos IATA de origen y destino (ejemplo: MEX, CUN), la fecha y el número de adultos.
- **Hoteles**: busca por ciudad y fechas. Por defecto usa Geoapify. Puedes cambiar el proveedor desde el `.env` con `HOTELS_PROVIDER=duffel` o `HOTELS_PROVIDER=rapidapi`.
- **Airbnb**: no tiene API pública, así que la app construye la URL de búsqueda con tus parámetros y la abre directamente en airbnb.com.
- **Chatbot**: está en la esquina inferior derecha. Puedes preguntarle recomendaciones de destinos, qué llevar en el viaje, etc.

Para acceder desde internet usando ngrok, agrega tu `NGROK_AUTHTOKEN` en el `.env` y ejecuta:

```bash
docker compose --profile tunnel up -d
```

La URL pública aparece en `http://localhost:4040`.

---

## Estructura del proyecto

```
atlas-guide/
├── app.py                 # Toda la lógica del backend (FastAPI)
├── index.html             # Interfaz principal
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── assets/                # Logo y fondo
└── static/                # JavaScript y CSS del frontend
    ├── flights.js
    ├── hotels.js
    ├── airbnb.js
    ├── chatbot.js
    ├── splash.js
    ├── tabs.js
    └── styles.css
```

---

## Funcionalidades principales

- Búsqueda de vuelos con resultados reales via Duffel API
- Búsqueda de hoteles con soporte para tres proveedores distintos
- Redirección a Airbnb con parámetros prellenados
- Chatbot de IA como asistente dentro de la misma interfaz
- Containerización completa, sin dependencias locales más allá de Docker
- Soporte para exposición pública vía ngrok

---

## Posibles mejoras

- Agregar autenticación de usuarios para guardar búsquedas
- Implementar caché en el backend para no repetir llamadas a las APIs
- Mejorar el chatbot con contexto de la búsqueda actual del usuario
- Agregar comparador de precios entre fechas
- Soporte para vuelos de ida y vuelta

---

## Autor

Miguel Emiliano Benítez Cedillo  
Estudiante de Ingeniería en Sistemas Computacionales — UNITEC Atizapán  
LinkedIn: linkedin.com/in/emiliano-benítez-cedillo-3399b5311  
GitHub: github.com/EmilianoBen
