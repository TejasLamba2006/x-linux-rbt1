# application/web-app/main.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI()

# Serve the static files from same backend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    return StaticFiles(directory="static", html=True)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print("Client connected")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print("Client disconnected")

    async def receive(self, websocket: WebSocket):
        try:
            while True:
                data = await websocket.receive_text()
                print(f"Received: {data}")
                # Put robot control functions here
                
        except WebSocketDisconnect:
            self.disconnect(websocket)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.receive(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)