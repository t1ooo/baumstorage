import asyncio
import os
from typing import Optional, Tuple
import logging
from fastapi import FastAPI, UploadFile, HTTPException
from pydantic import BaseModel
import uuid
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, func, select
import json


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI()

BIT = int(os.getenv("BIT"))
assert BIT in [0, 1]
KAFKA = os.getenv("KAFKA")
POSTGRESQL = os.getenv("POSTGRESQL")


producer = AIOKafkaProducer(bootstrap_servers=KAFKA)


@app.on_event("startup")
async def startup_event():
    await producer.start()
    loop.create_task(consume_count())
    loop.create_task(consume_save())


@app.on_event("shutdown")
async def shutdown_event():
    await producer.stop()


class Metadata(SQLModel, table=True):
    uuid: Optional[str] = Field(primary_key=True)
    filename: str
    size: int
    content_type: Optional[str] = None


def save_file(name: str, data: str):
    with open(name, "wb") as f:
        f.write(data.encode())


def load_file(name: str) -> bytes:
    with open(name, "rb") as f:
        return f.read()


class Storage:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, meta: Metadata, data: str):
        with Session(self.engine, expire_on_commit=True) as session:
            save_file(meta.uuid, data)
            session.add(meta)
            session.commit()

    def load(self, file_id: str) -> Tuple[Metadata, bytes]:
        with Session(self.engine, expire_on_commit=True) as session:
            data = load_file(file_id)
            statement = select(Metadata).where(Metadata.uuid == file_id)
            meta = session.exec(statement).first()
            return meta, data

    def total_size(self):
        with Session(self.engine, expire_on_commit=False) as session:
            return int(session.exec(func.sum(Metadata.size)).scalar() or 0)


engine = create_engine(POSTGRESQL)
storage = Storage(engine)
loop = asyncio.get_event_loop()
SQLModel.metadata.create_all(engine)


def count_bits(data: str, i: int):
    s = 0
    for b in data.encode():
        s += b == i
    return s


def extract_file_metadata(file: UploadFile) -> Metadata:
    return Metadata(
        uuid=str(uuid.uuid4()),
        filename=file.filename or "",
        size=file.size or 0,
        content_type=file.content_type,
    )


class Message(BaseModel):
    data: str
    meta: Metadata
    counts: list[int]


@app.get("/")
def read_root():
    return "OK"


class UploadResponse(BaseModel):
    metadata: Metadata


@app.post("/upload/")
async def upload(file: UploadFile):
    meta = extract_file_metadata(file)
    data = file.file.read().decode("latin-1")
    c = count_bits(data, BIT)
    counts = [-1, -1]
    counts[BIT] = c
    msg = Message(
        data=data,
        meta=meta,
        counts=counts,
    )
    data = msg.model_dump_json().encode("latin-1")
    await producer.send(f"count_{int(not BIT)}", data)
    return UploadResponse(metadata=meta)


class LoadResponse(BaseModel):
    metadata: Metadata
    data: str


@app.get("/file/{id}")
async def get_file(id: str):
    try:
        meta, data = storage.load(id)
        return UploadResponse(metadata=meta, data=data.decode("latin-1"))
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=404, detail="Item not found")


class SizeResponse(BaseModel):
    total_size: int


@app.get("/size/")
async def get_size(id: str):
    total_size = storage.total_size()
    return SizeResponse(total_size=total_size)


async def consume_count():
    consumer = AIOKafkaConsumer(f"count_{int(BIT)}", bootstrap_servers=KAFKA, loop=loop)

    await consumer.start()
    try:
        async for msg in consumer:
            msg = json.loads(msg.value.decode("latin-1"))
            msg = Message(**msg)
            assert msg.counts[BIT] == -1
            c = count_bits(msg.data, BIT)
            msg.counts[BIT] = c
            data = msg.model_dump_json().encode("latin-1")
            await producer.send("save", data)
    finally:
        await consumer.stop()


async def consume_save():
    consumer = AIOKafkaConsumer(f"save", bootstrap_servers=KAFKA, loop=loop)

    await consumer.start()
    try:
        async for msg in consumer:
            msg = json.loads(msg.value.decode("latin-1"))
            msg = Message(**msg)

            if msg.counts[0] > msg.counts[1]:
                if BIT == 0:
                    logger.info(f"{BIT}, {msg}")
                    storage.save(msg.meta, msg.data)
            elif msg.counts[0] < msg.counts[1]:
                if BIT == 1:
                    logger.info(f"{BIT}, {msg}")
                    storage.save(msg.meta, msg.data)
            else:
                logger.info(f"{BIT}, {msg}")
                storage.save(msg.meta, msg.data)
    finally:
        await consumer.stop()
