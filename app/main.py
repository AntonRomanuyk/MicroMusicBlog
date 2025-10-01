from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK

from app.models import Post

app = FastAPI()
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Hello World"}



@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

@app.post("/createpost")
def create_post(new_post: Post):
    try:
        print(new_post)
        return HTTP_201_CREATED
    except Exception as e:
        error_massage = "Failed to create post: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_massage)

@app.put("/updatepost/id/{id}")
def create_post(id: int, new_post: Post):
    try:
        print(f"{id} post was updated")
        print(new_post)
        return HTTP_200_OK
    except Exception as e:
        error_massage = "Failed to create post: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_massage)

@app.delete("/deletepost/id/{id}")
def delete_post(id: int):
    try:
        print(f"{id} post was deleted")
        return HTTP_204_NO_CONTENT
    except Exception as e:
        error_massage = "Failed to delete post: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_massage)

@app.get("/posts/id/{id}")
async def get_post(id: int):
    return {"message": f"{id} post"}

@app.get("/posts/latest")
async def get_latest_post():
    return {"message": "Latest Post"}

