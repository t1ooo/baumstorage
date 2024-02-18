from tempfile import TemporaryFile
import httpx
import time

URL_0 = "http://127.0.0.1:9000"
URL_1 = "http://127.0.0.1:9001"


def test_ones():
    with TemporaryFile() as f:
        f.write(b"\1\1\1\1\0\0")
        f.seek(0)

        response = httpx.post(f"{URL_1}/upload/", files={"file": ("1", f)})
        assert response.status_code == 200
        uuid = response.json()["metadata"]["uuid"]

        time.sleep(1)
        # file should exists
        response = httpx.get(f"{URL_1}/file/{uuid}")
        assert response.status_code == 200

        # file should't exists
        response = httpx.get(f"{URL_0}/file/{uuid}")
        assert response.status_code == 404


def test_ones_send_to_wrong_server():
    with TemporaryFile() as f:
        f.write(b"\1\1\1\1\0\0")
        f.seek(0)

        response = httpx.post(f"{URL_0}/upload/", files={"file": ("1", f)})
        assert response.status_code == 200
        uuid = response.json()["metadata"]["uuid"]

        time.sleep(1)
        # file should exists
        response = httpx.get(f"{URL_1}/file/{uuid}")
        assert response.status_code == 200

        # file should't exists
        response = httpx.get(f"{URL_0}/file/{uuid}")
        assert response.status_code == 404


def test_zeros():
    with TemporaryFile() as f:
        f.write(b"\0\0\0\0\1\1")
        f.seek(0)

        response = httpx.post(f"{URL_0}/upload/", files={"file": ("1", f)})
        assert response.status_code == 200
        uuid = response.json()["metadata"]["uuid"]

        time.sleep(1)
        # file should exists
        response = httpx.get(f"{URL_0}/file/{uuid}")
        assert response.status_code == 200

        # file should't exists
        response = httpx.get(f"{URL_1}/file/{uuid}")
        assert response.status_code == 404


def test_zeros_send_to_wrong_server():
    with TemporaryFile() as f:
        f.write(b"\0\0\0\0\1\1")
        f.seek(0)

        response = httpx.post(f"{URL_1}/upload/", files={"file": ("1", f)})
        assert response.status_code == 200
        uuid = response.json()["metadata"]["uuid"]

        time.sleep(1)
        # file should exists
        response = httpx.get(f"{URL_0}/file/{uuid}")
        assert response.status_code == 200

        # file should't exists
        response = httpx.get(f"{URL_1}/file/{uuid}")
        assert response.status_code == 404


def test_zeros_ones():
    with TemporaryFile() as f:
        f.write(b"\0\0\0\1\1\1")
        f.seek(0)

        response = httpx.post(f"{URL_0}/upload/", files={"file": ("1", f)})
        assert response.status_code == 200
        uuid = response.json()["metadata"]["uuid"]

        time.sleep(1)
        # file should exists
        response = httpx.get(f"{URL_0}/file/{uuid}")
        assert response.status_code == 200

        # file should exists
        response = httpx.get(f"{URL_1}/file/{uuid}")
        assert response.status_code == 200
