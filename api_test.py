# api.py
from fastapi import FastAPI
from system_info_test import get_system_info

app = FastAPI()

@app.get("/status")
def read_status():
    return get_system_info()
