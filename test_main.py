from fastapi.testclient import TestClient
import os
import pytest
from main import app

# 创建测试客户端
client = TestClient(app)

# 测试健康检查接口
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

# 测试根路径
def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

# 测试无效图片路径
def test_invalid_image_path():
    response = client.get("/images/nonexistent-image.jpg")
    assert response.status_code == 404
    assert "图片不存在" in response.json()["detail"]

# 测试图片列表接口
def test_list_images():
    response = client.get("/images")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

# 测试上传无效图片格式
def test_upload_invalid_format():
    # 模拟上传无效格式文件
    with open("test_main.py", "rb") as f:
        response = client.post(
            "/upload",
            files={"file": ("test.txt", f, "text/plain")}
        )
        assert response.status_code == 400
        assert "只允许上传" in response.json()["detail"] 