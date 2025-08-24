from pymilvus import connections, utility

# 1️⃣ Connect to Milvus
connections.connect(
    alias="default",
    host="milvus-standalone",  # or IP
    port="19530"
)

# 2️⃣ List all collections
collections = utility.list_collections()
print("Collections:", collections)

# 3️⃣ Get collection info
if collections:
    info = utility.get_collection_stats(collections[0])  # <-- updated method
    print(info)
