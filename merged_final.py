import cv2
import os
import json
import time
import hashlib
import requests
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox

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
    print("Waiting for job to complete...")
    progress_chars = ['|', '/', '-', '\\']
    progress_idx = 0
    
    while True:
        # Show a simple spinner in the console
        print(f"\rProcessing {progress_chars[progress_idx]}", end="")
        progress_idx = (progress_idx + 1) % len(progress_chars)
        
        time.sleep(1)
        response = requests.get(f"{url_pre}{url_job}/{job_id}", headers=HEADERS)
        job_response = response.json()
        if 'job' in job_response:
            job_dict = job_response['job']
            job_status = job_dict.get('status')
            
            if job_status in ['SUCCESS', 'FAILED']:
                print("\r", end="")  # Clear the spinner
                if job_status == 'SUCCESS':
                    image_url = job_dict['successInfo']['images'][0]['url']
                    print(f"Image generation successful!")
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

def generate_upscaled_image(resource_id):
    """
    Submit a job using the predefined workflow template with template ID 851732213811647787.
    Uses the uploaded image for upscaling and enhancement with default prompts.
    """
    if not resource_id:
        print("Error: No resource ID provided")
        return None
        
    # Generate a unique request ID
    request_id = hashlib.md5(str(int(time.time())).encode()).hexdigest()
    
    # Debug info
    print(f"Using resource ID: {resource_id}")
    
    # Default prompts
    positive_prompt = "photorealistic portrait, high resolution, detailed, sharp features"
    negative_prompt = "blurry, low quality, distorted, deformed, disfigured"
    
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
        
        # Print response details for debugging
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

def generate_face_swap(source_img_resource_id, target_img_resource_id):
    """
    Submit a job for face swapping using a custom ComfyUI face swap workflow.
    """
    request_id = hashlib.md5(str(int(time.time())).encode()).hexdigest()

    print(f"Source Face Resource ID: {source_img_resource_id}")
    print(f"Target Image Resource ID: {target_img_resource_id}")

    # Make all fieldValues strings for consistency
    data = {
        "request_id": request_id,
        "templateId": "851864232516407977",
        "params": {
            "async": False,
            "priority": "NORMAL",
            "extraParams": {}
        },
        "fields": {
            "fieldAttrs": [
                # Node that loads target image
                {"nodeId": "11", "fieldName": "image", "fieldValue": target_img_resource_id},
                
                # Node that loads source face image
                {"nodeId": "3", "fieldName": "image", "fieldValue": source_img_resource_id},
                
                # Optional: Node that loads the face model
                {"nodeId": "5", "fieldName": "ckpt_name", "fieldValue": "default.safetensors"},

                # Try with string values instead of boolean/numeric values
                {"nodeId": "2", "fieldName": "use_insightface", "fieldValue": "true"},
                {"nodeId": "2", "fieldName": "det_thresh", "fieldValue": "0.1"},
                {"nodeId": "2", "fieldName": "model", "fieldValue": "inswapper_128_fp16.onnx"},
                {"nodeId": "2", "fieldName": "det_size", "fieldValue": "1"},
                {"nodeId": "2", "fieldName": "det_model", "fieldValue": "retinaface_resnet50"},
            ]
        }
    }

    try:
        print("Submitting face swap job...")
        response = requests.post(f"{url_pre}{url_job}/workflow/template", json=data, headers=HEADERS)
        print(f"Response status: {response.status_code}")
        
        # Print full response for debugging
        print(f"Full response: {response.text}")
        
        response_data = response.json()
        
        if 'job' in response_data:
            job_id = response_data['job']['id']
            return get_job_result(job_id)
        else:
            print("Error: Job not created.")
            if 'error' in response_data:
                print(f"Error details: {response_data['error']}")
            return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def generate_image_to_image(resource_id, positive_prompt, style_value, negative_prompt=None):
    """
    Submit a job using the predefined workflow template with template ID 688362427502551075.
    Uses IPAdapter FaceID for image-to-image transformation with LoRA models.
    """
    if not resource_id:
        print("Error: No resource ID provided")
        return None
    
    # Use default negative prompt if none provided
    if not negative_prompt:
        negative_prompt = (
            "lowres, bad hands, text, error, missing fingers, extra digit, fewer digits, "
            "cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, "
            "watermark, username, blurry, patreon logo, artist name, sexual content, adult, nuidity"
        )
    
    # Generate a unique request ID
    request_id = hashlib.md5(str(int(time.time())).encode()).hexdigest()
    
    # Build the payload with all required field attributes
    data = {
        "request_id": request_id,
        "templateId": "688362427502551075",  # Template URL: https://tensor.art/template/688362427502551075
        "fields": {
            "fieldAttrs": [
                # Node 12: LoadImage (FACE)
                {"nodeId": "12", "fieldName": "image", "fieldValue": resource_id},
                # Node 25: SDXL Prompt Styler
                {"nodeId": "25", "fieldName": "style", "fieldValue": style_value},
                {"nodeId": "25", "fieldName": "text_positive", "fieldValue": positive_prompt},
                {"nodeId": "25", "fieldName": "text_negative", "fieldValue": negative_prompt},
                # Node 18: IPAdapter FaceID
                {"nodeId": "18", "fieldName": "weight", "fieldValue": "0.8"},
                # Node 3: KSampler (do not override the "model" pointer)
                {"nodeId": "3", "fieldName": "seed", "fieldValue": "161098661698898"},
                {"nodeId": "3", "fieldName": "cfg", "fieldValue": "2"},
                {"nodeId": "3", "fieldName": "steps", "fieldValue": "20"},
                {"nodeId": "3", "fieldName": "sampler_name", "fieldValue": "dpmpp_sde"},
                {"nodeId": "3", "fieldName": "scheduler", "fieldValue": "karras"},
                # Node 5: Empty Latent Image
                {"nodeId": "5", "fieldName": "width", "fieldValue": "1024"},
                {"nodeId": "5", "fieldName": "height", "fieldValue": "1024"},
                # Node 4: Load Checkpoint
                {"nodeId": "4", "fieldName": "ckpt_name", "fieldValue": "676746065682318967"},
                # Node 38: LoraLoaderModelOnly
                {"nodeId": "38", "fieldName": "lora_name", "fieldValue": "681174344216573550"},
                {"nodeId": "38", "fieldName": "strength_model", "fieldValue": "0.6"},
                {"nodeId": "38", "fieldName": "tams_lora_name", "fieldValue": "IP_adapter_face_id -  SDXL"}
            ]
        },
    }

    try:
        # Submit the job using the workflow template endpoint
        print("Submitting image-to-image transformation job...")
        response = requests.post(f"{url_pre}{url_job}/workflow/template", json=data, headers=HEADERS)
        
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
    padding = int(0.2 * h)  # 20% padding around the face
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

def select_image(title):
    """Open a file dialog to select an image file."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=[
            ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif"),
            ("All files", "*.*")
        ]
    )
    
    if file_path:
        return file_path
    return None

def main():
    """Main function with integrated workflow for face processing."""
    print("=" * 50)
    print("ADVANCED FACE PROCESSING TOOL")
    print("=" * 50)
    
    # Step 1: Select an image to work with
    print("\n=== STEP 1: SELECT AN IMAGE ===")
    image_path = select_image("Select an image to work with")
    
    if not image_path:
        print("No image selected. Exiting.")
        return
    
    # Display image info
    print(f"Selected image: {image_path}")
    
    # Step 2: Choose initial operation
    print("\n=== STEP 2: SELECT INITIAL OPERATION ===")
    print("1. Extract and Upscale Face")
    print("2. Exit")
    
    initial_choice = input("\nSelect an operation (1-2): ").strip()
    
    cropped_face_path = None
    
    if initial_choice == "1":
        # Face extraction workflow
        print("\n=== EXTRACTING FACE ===")
        output_path = input("Enter the desired output filename for the cropped face (or press Enter for 'cropped_face.jpg'): ").strip()
        if not output_path:
            output_path = 'cropped_face.jpg'
        
        cropped_face_path = crop_face(image_path, output_path)
        if not cropped_face_path:
            print("Face cropping failed. Exiting.")
            return
        
        # Show the cropped face
        print(f"Cropped face saved at: {cropped_face_path}")
        
        # Ask if user wants to upscale
        upscale_choice = input("\nDo you want to upscale the cropped face? (y/n): ").strip().lower()
        if upscale_choice == 'y':
            # Upload the cropped face
            print("\nUploading cropped face to TensorArt...")
            resource_id = upload_img(cropped_face_path)
            if not resource_id:
                print("Upload failed.")
                # Continue to next step even if upscaling fails
            else:
                # Process the image with default prompts
                print("\nProcessing image with TensorArt...")
                result_path = generate_upscaled_image(resource_id)
                
                if result_path:
                    print("\n" + "=" * 50)
                    print(f"SUCCESS! Upscaled face saved to: {result_path}")
                    print("=" * 50)
                    # Update the cropped_face_path to use the upscaled version
                    cropped_face_path = result_path
                else:
                    print("\nImage upscaling failed, continuing with original cropped face.")
        
        # After extraction (and optional upscaling), offer additional processing options
        print("\n=== SELECT ADDITIONAL PROCESSING ===")
        print("1. Face Swap")
        print("2. Image-to-Image with LoRA (Artistic Transformation)")
        print("3. Exit")
        
        process_choice = input("\nSelect a processing method (1-3): ").strip()
        
        # Adjust the choice numbers to match the new menu
        if process_choice == "1":
            process_choice = "2"  # Map to face swap
        elif process_choice == "2":
            process_choice = "3"  # Map to LoRA transformation
        elif process_choice == "3":
            process_choice = "4"  # Map to exit
    
    elif initial_choice == "2":
        print("Exiting program. Goodbye!")
        return
    
    else:
        print("Invalid choice. Exiting.")
        return
    
    if process_choice == "1":
        # Upscale & Enhance Face
        print("\n=== UPSCALING & ENHANCING FACE ===")
        
        # Upload the cropped face
        print("\nUploading cropped face to TensorArt...")
        resource_id = upload_img(cropped_face_path)
        if not resource_id:
            print("Upload failed. Exiting.")
            return
        
        # Process the image with default prompts
        print("\nProcessing image with TensorArt...")
        result_path = generate_upscaled_image(resource_id)
        
        if result_path:
            print("\n" + "=" * 50)
            print(f"SUCCESS! Final result saved to: {result_path}")
            print("=" * 50)
           
        else:
            print("\n" + "=" * 50)
            print("Image processing failed.")
            print("=" * 50)
    
    elif process_choice == "2":
        # Face Swap
        print("\n=== FACE SWAP ===")
        
        # We already have the source face from Step 1
        print("\nStep 1: Source face already extracted")
        source_path = cropped_face_path
        
        # Ask user to select target image
        print("\nStep 2: Select the TARGET image (the image where you want to place the face)")
        target_path = select_image("Select TARGET Image")
        if not target_path:
            print("No target image selected. Exiting.")
            return
        
        # Upload images
        print("\nUploading images to the server...")
        source_resource_id = upload_img(source_path)
        if not source_resource_id:
            print("Failed to upload source image. Exiting.")
            return
        
        target_resource_id = upload_img(target_path)
        if not target_resource_id:
            print("Failed to upload target image. Exiting.")
            return
        
        # Perform face swap
        print("\nProcessing face swap...")
        result_image_path = generate_face_swap(source_resource_id, target_resource_id)
        
        if result_image_path:
            print(f"\nFace swap completed successfully!")
            print(f"Result saved to: {result_image_path}")
            
        else:
            print("\nFace swap process failed.")
    
    elif process_choice == "3":
        # Image-to-Image with LoRA
        print("\n=== IMAGE-TO-IMAGE WITH LORA (ARTISTIC TRANSFORMATION) ===")
        
        # We already have the source face from Step 1
        print("\nUsing the extracted face for transformation")
        source_path = cropped_face_path
        
        # Upload the image
        print("\nUploading face to TensorArt...")
        resource_id = upload_img(source_path)
        if not resource_id:
            print("Upload failed. Exiting.")
            return
        
        # Get transformation parameters
        positive_prompt = input("\nEnter the description/prompt for the transformed image: ").strip()
        if not positive_prompt:
            positive_prompt = "masterpiece portrait, artistic style, vibrant"
        
        style_value = input("Enter the style for transformation (e.g., 'sai-line art', 'anime', 'digital art', etc.) or press Enter for default: ").strip()
        if not style_value:
            style_value = "sai-line art"
        
        negative_prompt = input("Enter a negative prompt (or press Enter for default): ").strip()
        if not negative_prompt:
            negative_prompt = (
                "lowres, bad hands, text, error, missing fingers, extra digit, fewer digits, "
                "cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, "
                "watermark, username, blurry, patreon logo, artist name"
            )
        
        # Process the image
        print("\nProcessing image with LoRA transformation...")
        result_path = generate_image_to_image(resource_id, positive_prompt, style_value, negative_prompt)
        
        if result_path:
            print("\n" + "=" * 50)
            print(f"SUCCESS! Transformed image saved to: {result_path}")
            print("=" * 50)
        else:
            print("\n" + "=" * 50)
            print("Image transformation failed.")
            print("=" * 50)
    
    elif process_choice == "4":
        print("Exiting program. Goodbye!")
        return
    
    else:
        print("Invalid choice. Please select a valid option.")
    
    # Ask if user wants to process another image
    another = input("\nDo you want to process another image? (y/n): ").strip().lower()
    if another == 'y':
        main()
    else:
        print("Exiting program. Goodbye!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")