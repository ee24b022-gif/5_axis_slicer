if __name__ == "__main__":

    import requests
    import json
    
    url = 'http://localhost:8001/slice_stl'
    files = {'file': open('test_overhang_auto.stl', 'rb')}
    data = {'auto_segment': 'True'}
    
    print("Uploading to API...")
    response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        print("Success! Parsing JSON...")
        # The API returns streaming JSON with string fragments. We need to handle it.
        try:
            content = response.text
            # We can just look for the strings if it's too large to parse fully or streaming isn't perfectly closed
            import re
            seg_match = re.search(r'"segmentation_info": ({[^}]+})', content)
            if seg_match:
                print("Segmentation Info:", seg_match.group(1))
                
            if "Retract\\n" in content:
                print("ERROR: literal \\n found in GCode string")
            elif "Retract\\n" not in content and "Retract" in content:
                print("SUCCESS: GCode contains proper retracts and newlines (escaped for JSON but not double escaped).")
                
        except Exception as e:
            print("Failed to parse response:", e)
    else:
        print(f"Error {response.status_code}: {response.text}")
