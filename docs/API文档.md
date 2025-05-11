# PicUI图床服务 API文档

## 🔌 API概览

PicUI提供了一组RESTful API，用于图片上传、查看、管理和生成短链接。所有API请求和响应均使用JSON格式。

## 🔑 认证说明

PicUI图床已移除用户系统，所有API接口均可直接访问，无需认证。

## 📑 API列表

### 图片上传

**请求：**
```
POST /upload
Content-Type: multipart/form-data
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| file  | File | 是 | 要上传的图片文件 |

**响应：**
```json
{
  "url": "http://example.com/images/abc123.jpg",
  "short_url": "http://example.com/s/xyz789",
  "filename": "abc123.jpg",
  "original_filename": "my_photo.jpg",
  "size": 256.5,
  "mime_type": "image/jpeg",
  "id": 42,
  "html_code": "<img src=\"http://example.com/images/abc123.jpg\" alt=\"my_photo.jpg\" />",
  "markdown_code": "![my_photo.jpg](http://example.com/images/abc123.jpg)"
}
```

**错误码：**
- 400: 不支持的图片格式或文件过大
- 403: 图片内容不符合规范
- 500: 服务器内部错误

---

### 图片删除

**请求：**
```
DELETE /img/{filename}
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| filename | String | 是 | 图片文件名 |

**响应：**
```json
{
  "success": true,
  "message": "图片已成功删除"
}
```

**错误码：**
- 404: 图片不存在
- 500: 服务器内部错误

---

### 访问图片

**请求：**
```
GET /images/{filename}
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| filename | String | 是 | 图片文件名 |

**响应：**
直接返回图片文件，Content-Type根据图片类型设置

**错误码：**
- 404: 图片不存在

---

### 获取带水印的图片

**请求：**
```
GET /images/{filename}/watermark
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| filename | String | 是 | 图片文件名 |
| text | String | 否 | 水印文字，默认为"PicUI图床" |
| position | String | 否 | 水印位置，可选：center, bottom-right, bottom-left, top-right, top-left，默认为bottom-right |
| opacity | Float | 否 | 水印不透明度，范围0.1-1.0，默认为0.5 |
| download | Boolean | 否 | 是否作为附件下载，默认为false |

**响应：**
直接返回添加水印后的图片，Content-Type根据原图片类型设置

**错误码：**
- 404: 图片不存在
- 500: 添加水印失败

---

### 访问短链接

**请求：**
```
GET /s/{code}
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| code | String | 是 | 短链接代码 |

**响应：**
重定向到原始图片URL

**错误码：**
- 404: 短链接不存在
- 410: 短链接已过期

---

### 创建临时外链

**请求：**
```
POST /create-temp-link/{image_id}
```

**参数：**
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| image_id | Integer | 是 | 图片ID |
| expire_minutes | Integer | 是 | 链接有效时间（分钟），范围1-10080（最长7天） |

**响应：**
```json
{
  "short_url": "http://example.com/s/abc123",
  "code": "abc123",
  "expire_at": "2023-05-15T12:34:56",
  "original_url": "http://example.com/images/file.jpg"
}
```

**错误码：**
- 404: 图片不存在

## 📊 系统监控API

### Prometheus指标

**请求：**
```
GET /metrics
```

**响应：**
返回Prometheus格式的监控指标

## 🌐 页面路由API

这些API主要返回HTML页面，适合在浏览器中直接访问：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页，图片上传界面 |
| `/admin` | GET | 管理面板 |
| `/admin/short-links` | GET | 短链接管理页面 |
| `/logs` | GET | 上传日志页面 |

## 💡 API使用示例

### 使用curl上传图片

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@/path/to/image.jpg"
```

### 使用Python上传图片

```python
import requests

url = "http://localhost:8000/upload"
files = {"file": open("image.jpg", "rb")}

response = requests.post(url, files=files)
data = response.json()
print(f"图片URL: {data['url']}")
print(f"短链接: {data['short_url']}")
```

### 使用JavaScript上传图片

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('http://localhost:8000/upload', {
  method: 'POST',
  body: formData,
})
.then(response => response.json())
.then(data => {
  console.log('上传成功:', data);
  console.log('图片URL:', data.url);
})
.catch(error => {
  console.error('上传失败:', error);
});
``` 