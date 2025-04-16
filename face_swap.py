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

def list_workflows():
    """List available workflow templates and their IDs."""
    try:
        response = requests.get(f"{url_pre}{url_workflow}/templates", headers=HEADERS)
        if response.status_code == 200:
            templates = response.json().get('templates', [])
            if templates:
                print("\nAvailable workflow templates:")
                for template in templates:
                    print(f"ID: {template.get('id')} - Name: {template.get('name')}")
                print("\nUse one of these IDs as your template_id in the generate_face_swap function.")
            else:
                print("No workflow templates found for your account.")
        else:
            print(f"Failed to retrieve workflows. Status code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error listing workflows: {e}")

def display_image(image_path):
    """Display the image using PIL."""
    try:
        img = Image.open(image_path)
        img.show()
    except Exception as e:
        print(f"Could not display image: {e}")

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
    """Interactive main function to run the face swap application."""
    print("=" * 50)
    print("         FACE SWAP APPLICATION         ")
    print("=" * 50)
    
    # Validate setup
    
    print("\nWelcome to the Face Swap application!")
    print("This program will help you swap faces between two images.")
    
    # Ask user to select source face image
    print("\nStep 1: Select the SOURCE face image (the face you want to use)")
    source_path = select_image("Select SOURCE Face Image")
    if not source_path:
        print("No source image selected. Exiting.")
        return
    
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
        
        # Ask if user wants to view the result
        view_choice = input("Would you like to view the result? (y/n): ").strip().lower()
        if view_choice == 'y':
            display_image(result_image_path)
    else:
        print("\nFace swap process failed.")
    
    print("\nThank you for using the Face Swap application!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        input("\nPress Enter to exit...")