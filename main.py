# --- Configuration ---
BASE_URL = "https://engine.prod.bria-api.com/v2"
API_TOKEN = "" 

# Initial text prompt for the VLM Bridge
INITIAL_PROMPT = "A hyper-detailed, ultra-fluffy owl sitting on a tree branch at night, looking directly at the camera with wide, adorable, expressive eyes."

# Refinement instruction for the VLM Bridge
REFINEMENT_PROMPT = "turn the scene into a daylight scene, with warm sunlight and golden highlights"

HEADERS = {
    "api_token": API_TOKEN,
    "Content-Type": "application/json"
}

# --- Helper Function for Asynchronous Polling ---
def poll_status(status_url):
    """Polls the status URL until the request is complete."""
    print(f"Polling status at: {status_url}")
    while True:
        time.sleep(5) # Wait 5 seconds between polls
        response = requests.get(status_url, headers=HEADERS)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'completed':
                print("Request completed successfully.")
                return result
            elif result.get('status') in ['failed', 'blocked']:
                print(f"Request failed or was blocked. Status: {result.get('status')}")
                print(json.dumps(result, indent=2))
                return None
            else:
                print(f"Status: {result.get('status')}. Waiting...")
        else:
            print(f"Error polling status: {response.status_code}")
            print(response.text)
            return None

# --- Step 1: Initial Structured Prompt Generation ---
def generate_initial_structured_prompt(prompt):
    """Generates the initial structured prompt from a text prompt."""
    print("\n--- Step 1: Generating Initial Structured Prompt ---")
    endpoint = f"{BASE_URL}/structured_prompt/generate"
    payload = {"prompt": prompt}
    
    response = requests.post(endpoint, headers=HEADERS, data=json.dumps(payload))
    
    if response.status_code == 202:
        status_url = response.json().get('status_url')
        result = poll_status(status_url)
        if result and result.get('result'):
            structured_prompt = result['result']['structured_prompt']
            print("Initial Structured Prompt generated.")
            return structured_prompt
    
    print("Failed to generate initial structured prompt.")
    return None

# --- Step 2: Iterative JSON Refinement ---
def refine_structured_prompt(structured_prompt, refinement_prompt):
    """Refines an existing structured prompt using a new text instruction."""
    print("\n--- Step 2: Refining Structured Prompt ---")
    endpoint = f"{BASE_URL}/structured_prompt/generate"
    payload = {
        "structured_prompt": structured_prompt,
        "prompt": refinement_prompt
    }
    
    response = requests.post(endpoint, headers=HEADERS, data=json.dumps(payload))
    
    if response.status_code == 202:
        status_url = response.json().get('status_url')
        result = poll_status(status_url)
        if result and result.get('result'):
            refined_structured_prompt = result['result']['structured_prompt']
            print("Structured Prompt refined.")
            return refined_structured_prompt
    
    print("Failed to refine structured prompt.")
    return None

# --- Step 3: Final Image Generation ---
def generate_final_image(structured_prompt):
    """Generates the final image using the refined structured prompt."""
    print("\n--- Step 3: Generating Final Image ---")
    endpoint = f"{BASE_URL}/image/generate"
    payload = {
        "structured_prompt": structured_prompt,
        "aspect_ratio": "1:1"
    }
    
    response = requests.post(endpoint, headers=HEADERS, data=json.dumps(payload))
    
    if response.status_code == 202:
        status_url = response.json().get('status_url')
        result = poll_status(status_url)
        if result and result.get('result'):
            image_url = result['result']['image_url']
            print(f"Final Image URL: {image_url}")
            return image_url
    
    print("Failed to generate final image.")
    return None

# --- Main Execution ---
if __name__ == "__main__":
    # 1. Generate Initial Structured Prompt
    initial_json = generate_initial_structured_prompt(INITIAL_PROMPT)
    
    if initial_json:
        print("\n--- Initial Structured Prompt (Excerpt) ---")
        # Parse and print a readable excerpt of the JSON
        parsed_json = json.loads(initial_json)
        print(f"Short Description: {parsed_json.get('short_description')}")
        print(f"Lighting Conditions: {parsed_json.get('lighting', {}).get('conditions')}")
        
        # 2. Refine the Structured Prompt
        refined_json = refine_structured_prompt(initial_json, REFINEMENT_PROMPT)
        
        if refined_json:
            print("\n--- Refined Structured Prompt (Excerpt) ---")
            # Verify the refinement (e.g., lighting should change from 'night'/'moonlight' to 'day'/'sunlight')
            parsed_refined_json = json.loads(refined_json)
            print(f"Short Description: {parsed_refined_json.get('short_description')}")
            print(f"Lighting Conditions: {parsed_refined_json.get('lighting', {}).get('conditions')}")
            
            # 3. Generate the Final Image
            final_image_url = generate_final_image(refined_json)
            
            if final_image_url:
                print("\n--- Workflow Complete ---")
                print(f"Final Image URL: {final_image_url}")