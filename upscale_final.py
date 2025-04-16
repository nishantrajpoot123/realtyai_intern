import cv2
import os
import json
import time
import hashlib
import requests
from PIL import Image

# API Details
url_pre = "https://ap-east-1.tensorart.cloud"
api_key = "38dbb245-327b-485c-bfdf-63ae966edb73"  # Replace with your actual API key
url_job = "/v1/jobs"
url_resource = "/v1/resource"
url_workflow = "/v1/workflows"

# Headers for API Key Authentication
HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {api_key}'
}

def ensure_output_folder():
    """Ensure that the 'outputs' folder exists."""
    if not os.path.exists("outputs"):
        os.makedirs("outputs")
    return "outputs"

def save_image(image_url):
    """Download and save the generated image. Return the saved image path."""
    output_dir = ensure_output_folder()
    response = requests.get(image_url)
    if response.status_code == 200:
        image_path = os.path.join(output_dir, f"{hashlib.md5(image_url.encode()).hexdigest()}.png")
        with open(image_path, "wb") as img_file:
            img_file.write(response.content)
        print(f"Image saved to {image_path}")
        return image_path
    else:
        print(f"Error downloading image: {response.status_code}")
        if hasattr(response, 'text'):
            print(f"Response content: {response.text}")
        return None

def get_job_result(job_id):
    """Poll the API for job completion status and return the output image path when complete."""
    while True:
        time.sleep(1)
        response = requests.get(f"{url_pre}{url_job}/{job_id}", headers=HEADERS)
        job_response = response.json()
        if 'job' in job_response:
            job_dict = job_response['job']
            job_status = job_dict.get('status')
            print("Job status:", job_dict)
            if job_status in ['SUCCESS', 'FAILED']:
                if job_status == 'SUCCESS':
                    image_url = job_dict['successInfo']['images'][0]['url']
                    print(f"Image URL: {image_url}")
                    print("Image generation successful.")
                    return save_image(image_url)
                else:
                    print("Image generation failed.")
                    if 'failureInfo' in job_dict:
                        print(f"Failure details: {job_dict['failureInfo']}")
                    return None

def upload_img(img_path):
    """Upload an image and return the resource ID."""
    print(f"Uploading image: {img_path}")
    
    # Check if the file exists
    if not os.path.exists(img_path):
        print(f"Error: File not found at {img_path}")
        return None
        
    data = {"expireSec": 3600}
    try:
        response = requests.post(f"{url_pre}{url_resource}/image", json=data, headers=HEADERS)
        response.raise_for_status()  # Raise exception for non-200 status codes
        
        response_data = response.json()
        resource_id = response_data['resourceId']
        put_url = response_data['putUrl']
        headers_upload = response_data['headers']

        with open(img_path, 'rb') as f:
            res = f.read()
            upload_response = requests.put(put_url, data=res, headers=headers_upload)
            upload_response.raise_for_status()

        print(f"Upload successful! Resource ID: {resource_id}")
        return resource_id
    except requests.exceptions.RequestException as e:
        print(f"Error during upload: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response content: {e.response.text}")
        return None

def generate_image(resource_id, positive_prompt, negative_prompt):
    """
    Submit a job using the predefined workflow template with template ID 851732213811647787.
    Uses the uploaded image along with prompts and style.
    """
    if not resource_id:
        print("Error: No resource ID provided")
        return None
        
    # Generate a unique request ID
    request_id = hashlib.md5(str(int(time.time())).encode()).hexdigest()
    
    # Debug info
    print(f"Using resource ID: {resource_id}")
    
    data = {
        "request_id": request_id,
        "templateId": "851732213811647787",
        "params": {   
            "async": False,
            "priority": "NORMAL",
            "extraParams": {}
        },
        "fields": {
            "fieldAttrs": [
                # Node 21: LoadImage
                {"nodeId": "21", "fieldName": "image", "fieldValue": resource_id},

                # Node 6: CLIPTextEncode (Positive Prompt)
                {"nodeId": "6", "fieldName": "text", "fieldValue": positive_prompt},

                # Node 7: CLIPTextEncode (Negative Prompt)
                {"nodeId": "7", "fieldName": "text", "fieldValue": negative_prompt},

                # Node 15: TensorArt_CheckpointLoader
                {"nodeId": "15", "fieldName": "ckpt_name", "fieldValue": "603269903807549991"},
                {"nodeId": "15", "fieldName": "model_name", "fieldValue": "EpiCRealism - pure Evo"},

                # Node 3: KSampler
                {"nodeId": "3", "fieldName": "seed", "fieldValue": "586515547860208"},
                {"nodeId": "3", "fieldName": "control_after_generate", "fieldValue": "fixed"},
                {"nodeId": "3", "fieldName": "steps", "fieldValue": "25"},
                {"nodeId": "3", "fieldName": "cfg", "fieldValue": "8"},
                {"nodeId": "3", "fieldName": "sampler_name", "fieldValue": "euler"},
                {"nodeId": "3", "fieldName": "scheduler", "fieldValue": "normal"},
                {"nodeId": "3", "fieldName": "denoise", "fieldValue": "0.15"},

                # Node 13: UpscaleModelLoader
                {"nodeId": "13", "fieldName": "model_name", "fieldValue": "4x_RealisticRescaler_100000_G.pth"},
                # Node 9: SaveImage
                {"nodeId": "9", "fieldName": "filename_prefix", "fieldValue": f"TensorArt_{request_id[:8]}"},
            ]
        },
    }
    
    try:
        # Debug - print the actual request body
        print("Request body (first 200 chars):", json.dumps(data)[:200], "...")
        
        # Submit the job
        print("Submitting job to TensorArt API...")
        response = requests.post(f"{url_pre}{url_job}/workflow/template", json=data, headers=HEADERS)
        
        # Print full response details regardless of success/failure
        print(f"Response status code: {response.status_code}")
        try:
            response_data = response.json()
            print(f"Response data: {json.dumps(response_data)[:500]}")
        except:
            print(f"Raw response content: {response.text[:500]}")
        
        response.raise_for_status()
        
        if 'job' in response_data:
            job_dict = response_data['job']
            job_id = job_dict.get('id')
            print(f"Workflow Job ID: {job_id}, Status: {job_dict.get('status')}")
            # Poll until the job is complete and then return the output image path
            return get_job_result(job_id)
        else:
            print("Failed to create workflow job:", response_data)
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error during job submission: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response content: {e.response.text}")
        return None


def crop_face(image_path, output_path='cropped_face.jpg'):
    """Detect faces in an image, let the user select one, and crop it."""
    img = cv2.imread(image_path)
    if img is None:
        print("Image not found. Please check the path and try again.")
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

    if len(faces) == 0:
        print("No faces detected in the image.")
        return None

    print(f"{len(faces)} face(s) detected.")
    for idx, (x, y, w, h) in enumerate(faces):
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(img, f'{idx}', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    cv2.imshow("Detected Faces - Press any key after noting the index", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    try:
        selected = int(input(f"Enter the index of the face to crop (0 to {len(faces)-1}): "))
        if selected < 0 or selected >= len(faces):
            print("Invalid index selected.")
            return None
    except ValueError:
        print("Invalid input. Please enter a number.")
        return None

    (x, y, w, h) = faces[selected]
    padding = int(0.2 * h)  # Keeping your original 20% padding
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img.shape[1], x + w + padding)
    y2 = min(img.shape[0], y + h + padding)

    face_img = cv2.imread(image_path)[y1:y2, x1:x2]
    face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB))
    face_pil = face_pil.resize((512, 512), Image.LANCZOS)
    face_pil.save(output_path, quality=95)

    print(f"✅ Face {selected} cropped and saved as: {output_path}")
    return output_path

def main():
    """Main function to orchestrate the face detection, cropping, and upscaling process."""
    print("=" * 50)
    print("FACE DETECTION AND UPSCALING TOOL")
    print("=" * 50)
    
    # Get input image path
    image_path = input("Enter the path to your input image: ").strip()
    if not image_path:
        print("Error: No image path provided.")
        return
        
    # Get output filename or use default
    output_path = input("Enter the desired output filename (or press Enter for 'cropped_face.jpg'): ").strip()
    if not output_path:
        output_path = 'cropped_face.jpg'
        
    # Crop the face
    cropped_face_path = crop_face(image_path, output_path)
    if not cropped_face_path:
        print("Face cropping failed. Exiting.")
        return
        
    # Ask if user wants to upscale the image
    while True:
        process_choice = input("Do you want to upscale the cropped face with TensorArt? (y/n): ").strip().lower()
        if process_choice in ('y', 'n'):
            break
        print("Please enter 'y' or 'n'.")
        
    if process_choice == 'n':
        print(f"Process completed. Cropped face saved at: {cropped_face_path}")
        return
        
    # Upload the cropped face
    print("\nUploading cropped face to TensorArt...")
    resource_id = upload_img(cropped_face_path)
    if not resource_id:
        print("Upload failed. Exiting.")
        return
        
    # Get prompts from user
    positive_prompt = input("\nEnter a positive prompt (or press Enter for none): ").strip()
    negative_prompt = input("Enter a negative prompt (or press Enter for none): ").strip()
    
    # Verify API parameters before submission
    print("\nVerifying TensorArt API parameters...")
    print(f"API Base URL: {url_pre}")
    print(f"API Key (first 5 chars): {api_key[:5]}...")
    print(f"Template ID: 851732213811647787")
 
    # Process the image
    print("\nProcessing image with TensorArt...")
    result_path = generate_image(resource_id, positive_prompt, negative_prompt)
    
    if result_path:
        print("\n" + "=" * 50)
        print(f"SUCCESS! Final result saved to: {result_path}")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("Image processing failed.")
        print("=" * 50)

if __name__ == "__main__":
    main()