"""Quick test: Gemini 2.5 Flash text + image."""
import os
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-2.5-flash")

# Test 1: Simple text
print("Test 1: Text generation...")
try:
    response = model.generate_content("Say hello in one word")
    print(f"  SUCCESS: {response.text}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 2: File upload
print("\nTest 2: File upload API...")
try:
    import io
    # Create a tiny test image
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    
    uploaded = genai.upload_file(buf, mime_type="image/jpeg", display_name="test")
    print(f"  Upload SUCCESS: {uploaded.name}")
    
    response = model.generate_content(["What do you see in this image?", uploaded])
    print(f"  Analysis SUCCESS: {response.text[:100]}")
    
    genai.delete_file(uploaded.name)
except Exception as e:
    print(f"  FAILED: {e}")

print("\nAll tests done.")
