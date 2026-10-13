"""
Avatar upload/list/delete endpoints.
"""

import io
import shutil

import pytest
from fastapi import HTTPException

from backend import main as bm


@pytest.fixture
def avatars_dir(tmp_path, monkeypatch):
    d = tmp_path / "avatars"
    d.mkdir()
    monkeypatch.setattr(bm, "AVATARS_DIR", d)
    return d


def _png_bytes(size=(200, 120), color=(200, 30, 30, 255)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _as_upload(data, filename="a.png", content_type="image/png"):
    from starlette.datastructures import UploadFile
    f = UploadFile(filename=filename, file=io.BytesIO(data))
    f.headers = {"content-type": content_type}
    return f


async def test_upload_resizes_to_square(avatars_dir):
    from PIL import Image
    res = await bm.upload_avatar(_as_upload(_png_bytes((400, 100))))
    assert res["status"] == "ok"
    path = avatars_dir / res["name"]
    assert path.is_file()
    with Image.open(path) as img:
        assert img.size == (bm.AVATAR_MAX_DIM, bm.AVATAR_MAX_DIM)


async def test_upload_rejects_non_image(avatars_dir):
    with pytest.raises(HTTPException) as e:
        await bm.upload_avatar(_as_upload(b"<html>", "x.html", "text/html"))
    assert e.value.status_code == 400


async def test_upload_rejects_empty_and_garbage(avatars_dir):
    with pytest.raises(HTTPException) as e:
        await bm.upload_avatar(_as_upload(b"", "e.png"))
    assert e.value.status_code == 400

    with pytest.raises(HTTPException) as e:
        await bm.upload_avatar(_as_upload(b"not really a png", "x.png"))
    assert e.value.status_code == 400


async def test_delete_and_list(avatars_dir):
    up = await bm.upload_avatar(_as_upload(_png_bytes()))
    listing = await bm.list_avatars()
    assert any(a["name"] == up["name"] for a in listing["avatars"])

    await bm.delete_avatar(up["name"])
    assert not (avatars_dir / up["name"]).exists()
    listing = await bm.list_avatars()
    assert not any(a["name"] == up["name"] for a in listing["avatars"])


async def test_delete_missing_404(avatars_dir):
    with pytest.raises(HTTPException) as e:
        await bm.delete_avatar("nope.png")
    assert e.value.status_code == 404


@pytest.mark.parametrize("bad", ["../.env", "..%2F.env", "sub/dir.png", "", "a b.png"])
async def test_path_traversal_blocked(avatars_dir, bad):
    with pytest.raises(HTTPException) as e:
        bm._avatar_path(bad)
    assert e.value.status_code == 400