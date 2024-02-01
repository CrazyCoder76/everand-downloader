import pymongo
import concurrent.futures
import subprocess
import shutil

# Replace these variables with your MongoDB connection details
mongo_host = "127.0.0.1"
mongo_port = 27017  # Default MongoDB port
mongo_database = "bookUrlList"
mongo_collection = "books"

# Create a MongoDB client
client = pymongo.MongoClient(host=mongo_host, port=mongo_port)
# Access your database
database = client[mongo_database]
# Access your collection
collection = database[mongo_collection]
all_documents = collection.find()

# Function to run script2.py and return "success" or "failed"
def run_script(argument):
    try:
        # Execute run.py
        book_id = argument["id"]
        book_title = argument["title"]
        book_url = argument["url"]
        cache_dir = book_url.split('/')[5]

        process = subprocess.Popen(["python", "run.py", book_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        # Check if run.py ran successfully
        if process.returncode == 0:
            return f"successfully download {book_id} {book_title}"
        else:
            shutil.rmtree(cache_dir)
            return f"failed download {book_id} {book_title}"
    except Exception as e:
        shutil.rmtree(cache_dir)
        return f"failed download {book_id} {book_title}"

# Number of total script2.py instances
total_instances = 2297673

# Number of instances to run concurrently
concurrent_limit = 2

# Create a ThreadPoolExecutor with the concurrent limit
with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_limit) as executor:
    # Submit tasks to run script2.py concurrently
    futures = [executor.submit(run_script, arg) for arg in all_documents]

    # Wait for all tasks to complete and print results
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        print(result)

# Don't forget to close the MongoDB connection when you're done
client.close()