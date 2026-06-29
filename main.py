import os
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from moviepy.editor import ImageClip, CompositeVideoClip
import numpy as np
from PIL import Image
from io import BytesIO

app = FastAPI()

# إعدادات Supabase - سيتم قراءتها من متغيرات البيئة بالسيرفر لأمان أعلى
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class VideoJob(BaseModel):
    job_id: str
    image_url: str

def render_loop_video(job_id: str, image_url: str):
    try:
        # 1. تحديث الحالة في Supabase إلى "جاري المعالجة والتقطيع"
        supabase.table("video_jobs").update({"status": "segmenting"}).eq("id", job_id).execute()
        
        # 2. تحميل الصورة من الرابط
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        img.save("temp_input.png")
        
        # 3. تحديث الحالة إلى "جاري الرندرة 4K"
        supabase.table("video_jobs").update({"status": "rendering"}).eq("id", job_id).execute()
        
        # --- [ملاحظة: هنا يتم فصل الطبقات تلقائياً، للتبسيط سنطبق حركة الـ Loop مباشرة] ---
        WIDTH, HEIGHT = 3840, 2160
        DURATION = 10
        FPS = 30
        
        # صناعة الفيديو ميكانيكياً وضمان الـ Loop بالمعادلات الرياضية
        bg_clip = ImageClip("temp_input.png").set_duration(DURATION).resize((WIDTH, HEIGHT))
        
        # معادلة التأرجح التلقائي للفيديو كاملاً أو العناصر (Pendulum Effect)
        def swing_effect(t):
            return 2 * np.sin(2 * np.pi * (2 / DURATION) * t) # دورة كاملة تنتهي عند الصفر تماماً
            
        final_clip = bg_clip.rotate(swing_effect, center=(WIDTH/2, HEIGHT/2))
        
        output_filename = f"{job_id}_output.mp4"
        final_clip.write_videofile(output_filename, fps=FPS, codec="libx264", bitrate="15000k")
        
        # 4. رفع الفيديو الناتج إلى Supabase Storage
        with open(output_filename, "rb") as f:
            supabase.storage.from_("videos").upload(
                path=output_filename,
                file=f,
                file_options={"content-type": "video/mp4"}
            )
            
        video_public_url = supabase.storage.from_("videos").get_public_url(output_filename)
        
        # 5. تحديث الحالة النهائية في الجدول وإضافة رابط الفيديو
        supabase.table("video_jobs").update({
            "status": "completed",
            "output_video_url": video_public_url
        }).eq("id", job_id).execute()
        
        # تنظيف الملفات المؤقتة من السيرفر
        os.remove("temp_input.png")
        os.remove(output_filename)
        
    except Exception as e:
        print(f"Error processing job {job_id}: {str(e)}")
        supabase.table("video_jobs").update({"status": "failed"}).eq("id", job_id).execute()

@app.post("/trigger-process/")
def start_processing(job: VideoJob, background_tasks: BackgroundTasks):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase credentials are not set on the server.")
        
    # تشغيل الرندرة في الخلفية عشان السيرفر ما يعلق ويعطي رد فوري للموقع
    background_tasks.add_task(render_loop_video, job.job_id, job.image_url)
    return {"status": "Processing started in background"}
