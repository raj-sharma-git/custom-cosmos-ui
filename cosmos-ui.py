import os
import io
import csv
import json
import uuid
import traceback
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, Blueprint
)
from flask_session import Session
from azure.identity import ClientSecretCredential
from azure.cosmos import CosmosClient, PartitionKey, exceptions as cosmos_exceptions
from openpyxl import Workbook, load_workbook

app = Flask(__name__)

# Server-side Session Configuration
# We place session files inside the workspace to keep the project self-contained and clean.
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=SESSION_DIR,
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=86400, # 24 hours
)
Session(app)

# In-memory store for active CosmosClient instances
CLIENT_STORE = {}

# ---------- Blueprint ----------
ui = Blueprint("ui", __name__, url_prefix="/cosmos-ui")

def get_store():
    sid = session.get("sid")
    return CLIENT_STORE.get(sid) if sid else None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def inner(*a, **kw):
        if not get_store():
            flash("Please login first to access this resource.", "warning")
            return redirect(url_for("ui.login"))
        return f(*a, **kw)
    return inner

# ---------- Helper Functions ----------
def get_partition_key_path(container):
    """Programmatically fetch the partition key path for a container."""
    try:
        properties = container.read()
        paths = properties.get("partitionKey", {}).get("paths", [])
        return paths[0] if paths else None
    except Exception as e:
        print(f"Error fetching partition key path: {e}")
        return "/id" # fallback

def extract_partition_key_value(item, pk_path):
    """Dynamically extract the partition key value from an item's attributes based on the path."""
    if not pk_path:
        return None
    parts = pk_path.strip("/").split("/")
    val = item
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return None
    return val

def build_search_query(search_mode, search_query):
    """
    Build Cosmos DB SQL query parts based on the search inputs.
    Returns: (where_clause, parameters_list)
    """
    if not search_query or not search_query.strip():
        return "", []

    search_query = search_query.strip()

    if search_mode == "advanced":
        # User provides a raw WHERE clause like "c.age > 21" or "c.category = 'Electronics'"
        # We strip initial 'WHERE' if they added it to be user friendly
        if search_query.upper().startswith("WHERE"):
            search_query = search_query[5:].strip()
        return f"WHERE {search_query}", []
    else:
        # Simple Search matches in ID or performs CONTAINS on string fields
        # Note: Cosmos DB supports CONTAINS(c.id, @search)
        where = "WHERE CONTAINS(LOWER(c.id), @search)"
        params = [{"name": "@search", "value": search_query.lower()}]
        return where, params

# ---------- Root Redirect ----------
@app.route("/")
def index_redirect():
    return redirect(url_for("ui.dashboard"))

# ---------- Routes ----------

@ui.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        auth_method = request.form.get("auth_method")
        endpoint = request.form.get("endpoint", "").strip()
        
        # Connection values
        conn_string = request.form.get("conn_string", "").strip()
        account_key = request.form.get("account_key", "").strip()
        
        # Service principal values
        tenant_id = request.form.get("tenant_id", "").strip()
        client_id = request.form.get("client_id", "").strip()
        client_secret = request.form.get("client_secret", "").strip()

        try:
            client = None
            auth_info = {}

            if auth_method == "conn_str":
                if not conn_string:
                    raise ValueError("Connection string is required.")
                client = CosmosClient.from_connection_string(conn_string)
                # Parse endpoint from conn_str for display
                for part in conn_string.split(";"):
                    if part.startswith("AccountEndpoint="):
                        auth_info["endpoint"] = part.replace("AccountEndpoint=", "")
                auth_info["method"] = "Connection String"
            
            elif auth_method == "key":
                if not endpoint or not account_key:
                    raise ValueError("Endpoint URI and Account Key are required.")
                client = CosmosClient(endpoint, credential=account_key)
                auth_info["endpoint"] = endpoint
                auth_info["method"] = "Account Key"
                
            elif auth_method == "sp":
                if not endpoint or not tenant_id or not client_id or not client_secret:
                    raise ValueError("All Service Principal fields are required.")
                credential = ClientSecretCredential(tenant_id, client_id, client_secret)
                client = CosmosClient(endpoint, credential=credential)
                auth_info["endpoint"] = endpoint
                auth_info["method"] = "Service Principal"
            else:
                raise ValueError("Invalid authentication method selected.")

            # Test connection by listing databases
            databases = list(client.list_databases())
            
            # Setup session
            sid = str(uuid.uuid4())
            session["sid"] = sid
            session["auth_info"] = auth_info
            
            # Store in CLIENT_STORE
            CLIENT_STORE[sid] = {
                "client": client,
                "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            flash("Successfully connected to Cosmos DB!", "success")
            return redirect(url_for("ui.dashboard"))

        except Exception as e:
            traceback.print_exc()
            flash(f"Connection failed: {str(e)}", "danger")
            return render_template("login.html")

    return render_template("login.html")

@ui.route("/logout")
def logout():
    sid = session.get("sid")
    if sid in CLIENT_STORE:
        del CLIENT_STORE[sid]
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("ui.login"))

@ui.route("/")
@ui.route("/dashboard")
@login_required
def dashboard():
    store = get_store()
    client = store["client"]
    try:
        databases = list(client.list_databases())
        db_tree = []
        for db in databases:
            db_client = client.get_database_client(db["id"])
            containers = list(db_client.list_containers())
            db_tree.append({
                "id": db["id"],
                "containers": [c["id"] for c in containers]
            })
        return render_template("dashboard.html", db_tree=db_tree, auth_info=session.get("auth_info"))
    except Exception as e:
        flash(f"Error fetching databases: {str(e)}", "danger")
        return render_template("dashboard.html", db_tree=[], auth_info=session.get("auth_info"))

@ui.route("/db/<db_id>/container/<container_id>")
@login_required
def container_view(db_id, container_id):
    store = get_store()
    client = store["client"]
    
    # Query parameters
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 10, type=int)
    search_mode = request.args.get("search_mode", "simple")
    search_query = request.args.get("search_query", "")

    offset = (page - 1) * limit

    try:
        # Get DB and Container Clients
        db_client = client.get_database_client(db_id)
        container = db_client.get_container_client(container_id)
        
        # Programmatically detect Partition Key
        pk_path = get_partition_key_path(container)
        
        # Build query parts
        where_clause, params = build_search_query(search_mode, search_query)
        
        # Get count query
        count_sql = f"SELECT VALUE COUNT(1) FROM c {where_clause}"
        count_iter = container.query_items(query=count_sql, parameters=params, enable_cross_partition_query=True)
        total_items = list(count_iter)[0] if count_iter else 0
        
        # Get items query
        # Standard query incorporates offset limit
        items_sql = f"SELECT * FROM c {where_clause} ORDER BY c.id OFFSET {offset} LIMIT {limit}"
        items_iter = container.query_items(query=items_sql, parameters=params, enable_cross_partition_query=True)
        items = list(items_iter)
        
        # Process items to extract partition key value and quick summaries
        processed_items = []
        for it in items:
            pk_val = extract_partition_key_value(it, pk_path)
            processed_items.append({
                "id": it.get("id"),
                "pk_val": pk_val,
                "raw": it
            })

        # Calculate pages
        total_pages = max(1, (total_items + limit - 1) // limit)

        # Database tree for sidebar quick-nav
        databases = list(client.list_databases())
        db_tree = []
        for db in databases:
            dbc = client.get_database_client(db["id"])
            db_tree.append({
                "id": db["id"],
                "containers": [c["id"] for c in dbc.list_containers()]
            })

        return render_template(
            "container.html",
            db_id=db_id,
            container_id=container_id,
            pk_path=pk_path,
            items=processed_items,
            page=page,
            limit=limit,
            search_mode=search_mode,
            search_query=search_query,
            total_items=total_items,
            total_pages=total_pages,
            db_tree=db_tree,
            auth_info=session.get("auth_info")
        )
    except Exception as e:
        traceback.print_exc()
        flash(f"Error querying container: {str(e)}", "danger")
        return redirect(url_for("ui.dashboard"))

# ---------- API Endpoints ----------

@ui.route("/api/db/<db_id>/container/<container_id>/item", methods=["POST"])
@login_required
def api_upsert_item(db_id, container_id):
    """Create or Update an item in Cosmos DB (Upsert)"""
    store = get_store()
    client = store["client"]
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        if "id" not in data or not str(data["id"]).strip():
            return jsonify({"status": "error", "message": "Document must contain an 'id' attribute."}), 400
            
        db_client = client.get_database_client(db_id)
        container = db_client.get_container_client(container_id)
        
        # Verify partition key exists in document
        pk_path = get_partition_key_path(container)
        pk_val = extract_partition_key_value(data, pk_path)
        if pk_val is None:
            clean_pk = pk_path.strip("/")
            return jsonify({
                "status": "error", 
                "message": f"Document must contain the partition key path attribute: '{clean_pk}'"
            }), 400
            
        # Execute Upsert
        res = container.upsert_item(body=data)
        return jsonify({"status": "success", "message": "Document saved successfully", "item": res})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/api/db/<db_id>/container/<container_id>/item/delete", methods=["POST"])
@login_required
def api_delete_item(db_id, container_id):
    """Delete an item from Cosmos DB"""
    store = get_store()
    client = store["client"]
    
    try:
        data = request.get_json()
        item_id = data.get("id")
        partition_key = data.get("partition_key")
        
        if not item_id:
            return jsonify({"status": "error", "message": "Item ID is required."}), 400

        db_client = client.get_database_client(db_id)
        container = db_client.get_container_client(container_id)
        
        # Delete item
        container.delete_item(item=item_id, partition_key=partition_key)
        return jsonify({"status": "success", "message": "Document deleted successfully."})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/db/<db_id>/container/<container_id>/export")
@login_required
def export_items(db_id, container_id):
    """Export container documents matching search filter to Excel or CSV"""
    store = get_store()
    client = store["client"]
    
    format_type = request.args.get("format", "csv").lower()
    search_mode = request.args.get("search_mode", "simple")
    search_query = request.args.get("search_query", "")

    try:
        db_client = client.get_database_client(db_id)
        container = db_client.get_container_client(container_id)
        
        where_clause, params = build_search_query(search_mode, search_query)
        sql = f"SELECT * FROM c {where_clause}"
        
        items = list(container.query_items(query=sql, parameters=params, enable_cross_partition_query=True))
        
        if not items:
            flash("No data found to export.", "warning")
            return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

        # Flatten items to construct standard key-value headers
        # Gather all unique keys from top-level fields
        headers = set()
        for it in items:
            headers.update(it.keys())
        # Put 'id' first for clean structure
        headers = sorted(list(headers))
        if "id" in headers:
            headers.remove("id")
            headers.insert(0, "id")

        if format_type == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "CosmosExport"
            
            # Write headers
            ws.append(headers)
            
            # Write rows
            for it in items:
                row = []
                for h in headers:
                    val = it.get(h, "")
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    row.append(val)
                ws.append(row)
                
            out = io.BytesIO()
            wb.save(out)
            out.seek(0)
            
            filename = f"cosmos_{container_id}_{datetime.now().strftime('%Y%m%d%H%S')}.xlsx"
            return send_file(
                out,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=filename
            )
            
        else: # CSV default
            out = io.StringIO()
            writer = csv.writer(out)
            
            # Headers
            writer.writerow(headers)
            
            # Rows
            for it in items:
                row = []
                for h in headers:
                    val = it.get(h, "")
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    row.append(val)
                writer.writerow(row)
                
            mem = io.BytesIO()
            mem.write(out.getvalue().encode("utf-8"))
            mem.seek(0)
            
            filename = f"cosmos_{container_id}_{datetime.now().strftime('%Y%m%d%H%S')}.csv"
            return send_file(
                mem,
                mimetype="text/csv",
                as_attachment=True,
                download_name=filename
            )

    except Exception as e:
        traceback.print_exc()
        flash(f"Export failed: {str(e)}", "danger")
        return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

@ui.route("/db/<db_id>/container/<container_id>/import", methods=["POST"])
@login_required
def import_items(db_id, container_id):
    """Import items from a CSV or Excel file"""
    store = get_store()
    client = store["client"]
    
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected for import.", "warning")
        return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

    try:
        db_client = client.get_database_client(db_id)
        container = db_client.get_container_client(container_id)
        pk_path = get_partition_key_path(container)
        clean_pk = pk_path.strip("/")

        imported_count = 0
        skipped_count = 0
        errors = []

        filename = file.filename.lower()
        rows = []
        headers = []

        file_bytes = file.stream.read()
        file_io = io.BytesIO(file_bytes)

        if filename.endswith(".csv"):
            stream = io.StringIO(file_bytes.decode("utf-8"), newline=None)
            reader = csv.reader(stream)
            headers = next(reader, None)
            if headers:
                for r in reader:
                    rows.append(r)
        elif filename.endswith(".xlsx"):
            wb = load_workbook(file_io, read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = next(rows_iter, None)
            if headers:
                for r in rows_iter:
                    rows.append(r)
        else:
            flash("Unsupported file format. Please upload a CSV or XLSX file.", "danger")
            return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

        if not headers:
            flash("Uploaded file is empty or missing headers.", "danger")
            return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

        for idx, row in enumerate(rows):
            try:
                # Build dict
                doc = {}
                for h_idx, h in enumerate(headers):
                    if h_idx < len(row) and h is not None:
                        val = row[h_idx]
                        # Try to parse stringified JSON lists/dicts
                        if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                            try:
                                val = json.loads(val)
                            except Exception:
                                pass
                        doc[h] = val

                # Ensure id exists or generate
                if "id" not in doc or not str(doc["id"]).strip():
                    doc["id"] = str(uuid.uuid4())

                # Ensure partition key path property exists
                pk_val = extract_partition_key_value(doc, pk_path)
                if pk_val is None:
                    # Inject a default or raise
                    doc[clean_pk] = "imported"
                
                # Upsert into Cosmos DB
                container.upsert_item(body=doc)
                imported_count += 1
            except Exception as item_err:
                skipped_count += 1
                errors.append(f"Row {idx+1}: {str(item_err)}")

        msg = f"Import Summary: {imported_count} documents imported successfully."
        if skipped_count > 0:
            msg += f" {skipped_count} items failed. Sample errors: {', '.join(errors[:3])}"
            flash(msg, "warning")
        else:
            flash(msg, "success")

    except Exception as e:
        traceback.print_exc()
        flash(f"Import process failed: {str(e)}", "danger")

    return redirect(url_for("ui.container_view", db_id=db_id, container_id=container_id))

@ui.route("/api/provision", methods=["POST"])
@login_required
def api_provision():
    """Provision a new Database and optionally a Container inside it"""
    store = get_store()
    client = store["client"]
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
            
        db_id = data.get("db_id", "").strip()
        container_id = data.get("container_id", "").strip()
        partition_key = data.get("partition_key", "").strip()
        
        if not db_id:
            return jsonify({"status": "error", "message": "Database ID is required."}), 400
            
        existing_dbs = {db["id"] for db in client.list_databases()}
        
        if container_id:
            if db_id in existing_dbs:
                db_client = client.get_database_client(db_id)
                existing_containers = {c["id"] for c in db_client.list_containers()}
                if container_id in existing_containers:
                    return jsonify({"status": "error", "message": f"Container '{container_id}' already exists in database '{db_id}'."}), 400
            
            client.create_database_if_not_exists(id=db_id)
            
            if not partition_key:
                partition_key = "/id"
            if not partition_key.startswith("/"):
                partition_key = "/" + partition_key
                
            db_client = client.get_database_client(db_id)
            db_client.create_container_if_not_exists(
                id=container_id,
                partition_key=PartitionKey(path=partition_key)
            )
            msg = f"Successfully provisioned database '{db_id}' and container '{container_id}'."
        else:
            if db_id in existing_dbs:
                return jsonify({"status": "error", "message": f"Database '{db_id}' already exists."}), 400
                
            client.create_database_if_not_exists(id=db_id)
            msg = f"Successfully created database '{db_id}'."
            
        return jsonify({
            "status": "success", 
            "message": msg
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/api/db/<db_id>/delete", methods=["POST"])
@login_required
def api_delete_database(db_id):
    """Delete a Database from Cosmos DB"""
    store = get_store()
    client = store["client"]
    try:
        client.delete_database(db_id)
        return jsonify({"status": "success", "message": f"Database '{db_id}' deleted successfully."})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/api/db/<db_id>/container/<container_id>/delete", methods=["POST"])
@login_required
def api_delete_container(db_id, container_id):
    """Delete a Container from a Database"""
    store = get_store()
    client = store["client"]
    try:
        db_client = client.get_database_client(db_id)
        db_client.delete_container(container_id)
        return jsonify({"status": "success", "message": f"Container '{container_id}' deleted successfully from database '{db_id}'."})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/api/bulk-check", methods=["POST"])
@login_required
def api_bulk_check():
    """Parse bulk upload file and check for existing databases"""
    store = get_store()
    client = store["client"]
    
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"status": "error", "message": "No file provided"}), 400
        
    try:
        filename = file.filename.lower()
        rows = []
        headers = []
        
        file_bytes = file.stream.read()
        file_io = io.BytesIO(file_bytes)

        if filename.endswith(".csv"):
            stream = io.StringIO(file_bytes.decode("utf-8"), newline=None)
            reader = csv.reader(stream)
            headers = next(reader, None)
            if headers:
                for r in reader:
                    rows.append(r)
        elif filename.endswith(".xlsx"):
            wb = load_workbook(file_io, read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = next(rows_iter, None)
            if headers:
                for r in rows_iter:
                    rows.append(r)
        else:
            return jsonify({"status": "error", "message": "Unsupported file format"}), 400
            
        if not headers:
            return jsonify({"status": "error", "message": "File is empty or missing headers"}), 400
            
        db_idx = -1
        for h_idx, h in enumerate(headers):
            if h is None:
                continue
            h_str = str(h).strip().lower()
            if h_str in ["db_name", "database_name", "database", "db", "dbname"]:
                db_idx = h_idx
        
        if db_idx == -1 and len(headers) > 0:
            db_idx = 0
            
        uploaded_dbs = set()
        for row in rows:
            if not row or all(v is None for v in row):
                continue
            db_name = str(row[db_idx]).strip() if db_idx < len(row) and row[db_idx] is not None else ""
            if db_name:
                uploaded_dbs.add(db_name)
                
        existing_cosmos_dbs = {db["id"] for db in client.list_databases()}
        overlap = list(uploaded_dbs.intersection(existing_cosmos_dbs))
        
        return jsonify({"status": "success", "existing_dbs": overlap})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@ui.route("/bulk-create", methods=["POST"])
@login_required
def bulk_create_dbs_containers():
    """Bulk provision databases and containers from CSV or Excel (.xlsx) file"""
    store = get_store()
    client = store["client"]
    
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected for bulk creation.", "warning")
        return redirect(url_for("ui.dashboard"))
        
    try:
        filename = file.filename.lower()
        rows = []
        headers = []
        
        file_bytes = file.stream.read()
        file_io = io.BytesIO(file_bytes)

        if filename.endswith(".csv"):
            stream = io.StringIO(file_bytes.decode("utf-8"), newline=None)
            reader = csv.reader(stream)
            headers = next(reader, None)
            if headers:
                for r in reader:
                    rows.append(r)
        elif filename.endswith(".xlsx"):
            wb = load_workbook(file_io, read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = next(rows_iter, None)
            if headers:
                for r in rows_iter:
                    rows.append(r)
        else:
            flash("Unsupported file format. Please upload a CSV or XLSX file.", "danger")
            return redirect(url_for("ui.dashboard"))
            
        if not headers:
            flash("Uploaded file is empty or missing headers.", "danger")
            return redirect(url_for("ui.dashboard"))
            
        # Standardize headers to find indices
        db_idx, container_idx, pk_idx = -1, -1, -1
        for h_idx, h in enumerate(headers):
            if h is None:
                continue
            h_str = str(h).strip().lower()
            if h_str in ["db_name", "database_name", "database", "db", "dbname"]:
                db_idx = h_idx
            elif h_str in ["container_name", "container", "collection", "containername"]:
                container_idx = h_idx
            elif h_str in ["partition_key", "partition_path", "partitionkey", "pk", "partitionkeypath"]:
                pk_idx = h_idx
                
        # Robust positions fallback if header names aren't matched
        if db_idx == -1 and len(headers) > 0:
            db_idx = 0
        if container_idx == -1 and len(headers) > 1:
            container_idx = 1
        if pk_idx == -1 and len(headers) > 2:
            pk_idx = 2
            
        created_dbs = set()
        created_containers = []
        errors = []
        
        for idx, row in enumerate(rows):
            if not row or all(v is None for v in row):
                continue
                
            try:
                db_name = str(row[db_idx]).strip() if db_idx < len(row) and row[db_idx] is not None else ""
                container_name = str(row[container_idx]).strip() if container_idx < len(row) and row[container_idx] is not None else ""
                partition_key = str(row[pk_idx]).strip() if (pk_idx != -1 and pk_idx < len(row) and row[pk_idx] is not None) else "/id"
                
                if not db_name or not container_name:
                    continue
                    
                mode = request.form.get("mode", "merge")
                
                # Create Database if not exists
                if mode == "overwrite" and db_name not in created_dbs:
                    try:
                        client.get_database_client(db_name).read()
                        client.delete_database(db_name)
                    except exceptions.CosmosResourceNotFoundError:
                        pass

                client.create_database_if_not_exists(id=db_name)
                created_dbs.add(db_name)
                
                # Clean Partition Key
                pk_path = partition_key if partition_key else "/id"
                if not pk_path.startswith("/"):
                    pk_path = "/" + pk_path
                    
                # Create Container if not exists
                db_client = client.get_database_client(db_name)
                db_client.create_container_if_not_exists(
                    id=container_name,
                    partition_key=PartitionKey(path=pk_path)
                )
                created_containers.append(f"{db_name}/{container_name}")
                
            except Exception as row_err:
                errors.append(f"Row {idx+2}: {str(row_err)}")
                
        msg = f"Bulk Process Complete! Verified/Created {len(created_dbs)} databases and {len(created_containers)} containers."
        if errors:
            msg += f" Encountered {len(errors)} errors. Sample errors: {', '.join(errors[:3])}"
            flash(msg, "warning")
        else:
            flash(msg, "success")
            
    except Exception as e:
        traceback.print_exc()
        flash(f"Bulk creation failed: {str(e)}", "danger")
        
    return redirect(url_for("ui.dashboard"))

# Register blueprint
app.register_blueprint(ui)

# ---------- Run App ----------
if __name__ == "__main__":
    # Local dev server runs on 5001 to prevent conflicts
    app.run(host="0.0.0.0", port=5001, debug=True)