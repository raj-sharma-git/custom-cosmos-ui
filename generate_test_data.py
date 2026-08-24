import json
import uuid
import random

def generate_sample_dataset(count=500, json_file="sample_import_500.json", jsonl_file="sample_import_500.jsonl"):
    categories = [
        "Electronics", "Home & Kitchen", "Books", "Clothing",
        "Sports & Outdoors", "Beauty & Health", "Toys & Games", "Automotive"
    ]
    cities = [
        "New York", "San Francisco", "Seattle", "Chicago", "Austin",
        "Boston", "Los Angeles", "Denver", "Miami", "Atlanta",
        "Dallas", "Phoenix", "Portland", "San Diego", "Houston"
    ]
    tags_pool = [
        "featured", "discount", "trending", "bestseller",
        "new-arrival", "eco-friendly", "limited-edition", "clearance", "premium"
    ]
    statuses = ["active", "pending", "archived", "out_of_stock"]

    documents = []
    print(f"Generating {count} sample documents...")

    for i in range(1, count + 1):
        cat = random.choice(categories)
        city = random.choice(cities)
        doc_id = f"doc_{i:04d}_{uuid.uuid4().hex[:8]}"
        
        doc = {
            "id": doc_id,
            "itemNumber": i,
            "title": f"{cat} Product #{i}",
            "category": cat,
            "city": city,
            "price": round(random.uniform(9.99, 1499.99), 2),
            "inStock": random.choice([True, True, True, False]),
            "quantity": random.randint(0, 500),
            "rating": round(random.uniform(1.0, 5.0), 1),
            "status": random.choice(statuses),
            "tags": random.sample(tags_pool, k=random.randint(1, 3)),
            "metadata": {
                "sku": f"SKU-{cat[:3].upper()}-{i:05d}",
                "weight_kg": round(random.uniform(0.1, 30.0), 2),
                "supplier": f"Supplier-{random.randint(1, 25)}",
                "warehouse": f"WH-{city[:3].upper()}-01"
            }
        }
        documents.append(doc)

    # 1. Write as JSON Array (Standard .json)
    if json_file:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(documents, f, indent=2)
        print(f" Saved JSON array to '{json_file}' ({len(documents)} items)")

    # 2. Write as JSON Lines (.jsonl / .ndjson)
    if jsonl_file:
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for d in documents:
                f.write(json.dumps(d) + "\n")
        print(f" Saved JSON Lines to '{jsonl_file}' ({len(documents)} items)")

    return documents

if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    generate_sample_dataset(count=count)
