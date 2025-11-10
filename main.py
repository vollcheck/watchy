from fastapi import FastAPI, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from datetime import datetime
from typing import Optional, List
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
DATABASE_PATH = "footage_tracker.db"
WATCH_DIRECTORY = "./footage"  # Change this to your footage directory

app = FastAPI(title="Footage Tracker API")


# Database setup
def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Files/Directories table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            parent_directory TEXT NOT NULL,
            file_type TEXT NOT NULL,  -- 'image', 'video', 'directory'
            size_bytes INTEGER,
            created_at TIMESTAMP NOT NULL,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT FALSE,
            processed_at TIMESTAMP,
            is_directory BOOLEAN DEFAULT FALSE
        )
    """)

    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed ON files(processed)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_type ON files(file_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent_dir ON files(parent_directory)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_path ON files(path)")

    conn.commit()
    conn.close()


def get_file_type(path: Path) -> str:
    """Determine file type based on extension"""
    if path.is_dir():
        return "directory"

    extension = path.suffix.lower()
    image_extensions = {'.jpg', '.jpeg'}
    video_extensions = {'.mp4', '.blk'}

    if extension in image_extensions:
        return "image"
    elif extension in video_extensions:
        return "video"
    else:
        return "other"


def insert_file_to_db(file_path: Path):
    """Insert file/directory information into database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        is_directory = file_path.is_dir()
        file_type = get_file_type(file_path)
        size_bytes = 0 if is_directory else file_path.stat().st_size
        created_at = datetime.fromtimestamp(file_path.stat().st_ctime)

        cursor.execute("""
            INSERT OR IGNORE INTO files
            (path, filename, parent_directory, file_type, size_bytes, created_at, is_directory)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(file_path.absolute()),
            file_path.name,
            str(file_path.parent.absolute()),
            file_type,
            size_bytes,
            created_at,
            is_directory
        ))

        conn.commit()
        conn.close()
        print(f"✓ Tracked: {file_path} (type: {file_type})")
    except Exception as e:
        print(f"✗ Error tracking {file_path}: {e}")


class FootageEventHandler(FileSystemEventHandler):
    """Watchdog event handler for filesystem monitoring"""

    def on_created(self, event):
        """Handle file/directory creation events"""
        if event.is_directory:
            print(f"Directory created: {event.src_path}")
        else:
            print(f"File created: {event.src_path}")

        file_path = Path(event.src_path)
        insert_file_to_db(file_path)

    def on_moved(self, event):
        """Handle file/directory move events"""
        print(f"Moved: {event.src_path} -> {event.dest_path}")
        # You might want to update the database here
        file_path = Path(event.dest_path)
        insert_file_to_db(file_path)


# Global observer instance
observer: Optional[Observer] = None


def start_filesystem_monitor():
    """Start watchdog observer in a separate thread"""
    global observer

    # Ensure watch directory exists
    watch_path = Path(WATCH_DIRECTORY)
    watch_path.mkdir(parents=True, exist_ok=True)

    event_handler = FootageEventHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()
    print(f"Watching directory: {watch_path.absolute()}")


def stop_filesystem_monitor():
    """Stop watchdog observer"""
    global observer
    if observer:
        observer.stop()
        observer.join()
        print("Stopped filesystem monitoring")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    print("Starting Watchy API...")
    init_database()
    start_filesystem_monitor()

    yield

    # Shutdown
    print("Shutting down...")
    stop_filesystem_monitor()


app = FastAPI(title="Footage Tracker API", lifespan=lifespan)


# API Endpoints

@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "message": "Footage Tracker API",
        "watch_directory": str(Path(WATCH_DIRECTORY).absolute()),
        "database": DATABASE_PATH
    }


@app.get("/stats")
def get_stats():
    """Get statistics about tracked files"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    stats = {}

    # Total files
    cursor.execute("SELECT COUNT(*) FROM files WHERE is_directory = FALSE")
    stats["total_files"] = cursor.fetchone()[0]

    # Total directories
    cursor.execute("SELECT COUNT(*) FROM files WHERE is_directory = TRUE")
    stats["total_directories"] = cursor.fetchone()[0]

    # Processed vs unprocessed
    cursor.execute("SELECT COUNT(*) FROM files WHERE processed = TRUE AND is_directory = FALSE")
    stats["processed_files"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM files WHERE processed = FALSE AND is_directory = FALSE")
    stats["unprocessed_files"] = cursor.fetchone()[0]

    # By file type
    cursor.execute("SELECT file_type, COUNT(*) FROM files WHERE is_directory = FALSE GROUP BY file_type")
    stats["by_type"] = dict(cursor.fetchall())

    # Total size
    cursor.execute("SELECT SUM(size_bytes) FROM files WHERE is_directory = FALSE")
    total_bytes = cursor.fetchone()[0] or 0
    stats["total_size_mb"] = round(total_bytes / (1024 * 1024), 2)

    conn.close()
    return stats


@app.get("/files/unprocessed")
def get_unprocessed_files(limit: int = 100, file_type: Optional[str] = None):
    """Get list of unprocessed files (queue)"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if file_type:
        cursor.execute("""
            SELECT * FROM files
            WHERE processed = FALSE AND is_directory = FALSE AND file_type = ?
            ORDER BY discovered_at ASC
            LIMIT ?
        """, (file_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM files
            WHERE processed = FALSE AND is_directory = FALSE
            ORDER BY discovered_at ASC
            LIMIT ?
        """, (limit,))

    files = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        "count": len(files),
        "files": files
    }


@app.get("/files/search")
def search_files(
    filename: Optional[str] = None,
    directory: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 100
):
    """Search for files by various criteria"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM files WHERE is_directory = FALSE"
    params = []

    if filename:
        query += " AND filename LIKE ?"
        params.append(f"%{filename}%")

    if directory:
        query += " AND parent_directory LIKE ?"
        params.append(f"%{directory}%")

    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)

    query += " ORDER BY discovered_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    files = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        "count": len(files),
        "files": files
    }


@app.post("/process/{file_id}")
def mark_as_processed(file_id: int):
    """Mark a file as processed"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE files
        SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (file_id,))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")

    conn.commit()
    conn.close()

    return {"message": f"File {file_id} marked as processed"}


@app.post("/process/batch")
def process_batch(file_ids: List[int]):
    """Mark multiple files as processed"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    placeholders = ",".join("?" * len(file_ids))
    cursor.execute(f"""
        UPDATE files
        SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
    """, file_ids)

    updated_count = cursor.rowcount
    conn.commit()
    conn.close()

    return {
        "message": f"Marked {updated_count} files as processed",
        "count": updated_count
    }


@app.post("/scan/initial")
def initial_scan():
    """
    Perform initial scan of the watch directory.
    Use this to populate the database with existing files.
    """
    watch_path = Path(WATCH_DIRECTORY)

    if not watch_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {watch_path}")

    added_count = 0

    def scan_recursive(path: Path):
        nonlocal added_count
        try:
            for item in path.iterdir():
                insert_file_to_db(item)
                added_count += 1

                if item.is_dir():
                    scan_recursive(item)
        except PermissionError as e:
            print(f"Permission denied: {path}")

    scan_recursive(watch_path)

    return {
        "message": "Initial scan completed",
        "items_added": added_count,
        "directory": str(watch_path.absolute())
    }


@app.post("/process/simulate")
async def simulate_processing(background_tasks: BackgroundTasks, batch_size: int = 10):
    """
    Simulate processing of unprocessed files.
    In the future, this will be replaced with actual processing logic.
    """

    def process_files():
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Get unprocessed files
        cursor.execute("""
            SELECT id, path, filename FROM files
            WHERE processed = FALSE AND is_directory = FALSE
            LIMIT ?
        """, (batch_size,))

        files = cursor.fetchall()

        for file_id, path, filename in files:
            print(f"Processing: {filename}")
            # Simulate some processing time
            time.sleep(0.1)

            # Mark as processed
            cursor.execute("""
                UPDATE files
                SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (file_id,))

        conn.commit()
        processed_count = len(files)
        conn.close()

        print(f"Processed {processed_count} files")

    background_tasks.add_task(process_files)

    return {
        "message": f"Processing {batch_size} files in background",
        "batch_size": batch_size
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
