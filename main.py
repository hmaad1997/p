import os
import requests
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from moviepy.editor import ImageClip
import numpy as np
from PIL import Image
from io import BytesIO

app = FastAPI()

# تعريف متغير السيرفر بدون استدعاء فوري لتجنب كراش الإقلاع
supabase: Client = None

@app.on_event("startup")
def startup_event():
    global supabase
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ WARNING: Supabase credentials are missing from Environment Variables!")
        return
        
    try:
        supabase = create_client(url, key)
        print("Context: 🌍 Connected to Supabase successfully during startup.")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {str(e)}")

class VideoJob(BaseModel):
    job_id: str
    image_url: str

def render_loop_video(job_id: str, image_url: str):
    if supabase is None:
        print("❌ Error: Supabase client is not initialized.")
        return
        
    try:
        supabase.table("video_jobs").update({"status": "segmenting"}).eq("id", job_id).execute()
        
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        img.save("temp_input.png")
        
        supabase.table("video_jobs").update({"status": "rendering"}).eq("id", job_id).execute()
        
        WIDTH, HEIGHT = 3840, 2160
        DURATION = 10
        FPS = 30
        
        bg_clip = ImageClip("temp_input.png").set_duration(DURATION).resize((WIDTH, HEIGHT))
        
        def swing_effect(t):
            return 2 * np.sin(2 * np.pi * (2 / DURATION) * t)
            
        final_clip = bg_clip.rotate(swing_effect, center=(WIDTH/2, HEIGHT/2))
        
        output_filename = f"{job_id}_output.mp4"
        final_clip.write_videofile(output_filename, fps=FPS, codec="libx264", bitrate="15000k")
        
        with open(output_filename, "rb") as f:
            supabase.storage.from_("videos").upload(
                path=output_filename,
                file=f,
                file_options={"content-type": "video/mp4"}
            )
            
        video_public_url = supabase.storage.from_("videos").get_public_url(output_filename)
        
        supabase.table("video_jobs").update({
            "status": "completed",
            "output_video_url": video_public_url
        }).eq("id", job_id).execute()
        
        os.remove("temp_input.png")
        os.remove(output_filename)
        
    except Exception as e:
        print(f"Error processing job {job_id}: {str(e)}")
        try:
            supabase.table("video_jobs").update({"status": "failed"}).eq("id", job_id).execute()
        except:
            pass

@app.post("/trigger-process/")
def start_processing(job: VideoJob, background_tasks: BackgroundTasks):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Backend engine is live but Supabase connection is uninitialized.")
    
    background_tasks.add_task(render_loop_video, job.job_id, job.image_url)
    return {"status": "Processing started in background"}
