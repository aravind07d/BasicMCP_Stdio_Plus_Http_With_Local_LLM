
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, yaml

with open("app/config/settings.yaml", "r") as f:
    cfg = yaml.safe_load(f)

HOST = cfg["servers"]["rest_host"]
PORT = cfg["servers"]["rest_port"]

app = FastAPI(title="Basic REST API")

class MathRequest(BaseModel):
    a: float
    b: float

@app.get("/hello")
def hello():
    return {"message": "Hello from REST API!"}

@app.post("/add")
def add_numbers(request: MathRequest):
    result = request.a + request.b
    return {"result": result}

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
