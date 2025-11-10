# Crucial parts

1. Observer declaration:

https://github.com/vollcheck/watchy/blob/master/main.py#L123

```python
observer: Optional[Observer] = None
```

2. Inherit from Event Handler for file system events

https://github.com/vollcheck/watchy/blob/master/main.py#L101

```python
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
```

# Result
```
Directory created: footage/df215d4f-fa6e-427a-981a-2218f66707a7
Tracked: footage/df215d4f-fa6e-427a-981a-2218f66707a7 (type: directory)
Directory created: footage/df215d4f-fa6e-427a-981a-2218f66707a7/ec8168ce-2f62-4e9f-9f6f-613363ae6036
Tracked: footage/df215d4f-fa6e-427a-981a-2218f66707a7/ec8168ce-2f62-4e9f-9f6f-613363ae6036 (type: directory)
File created: footage/df215d4f-fa6e-427a-981a-2218f66707a7/ec8168ce-2f62-4e9f-9f6f-613363ae6036/frame0.blk
Tracked: footage/df215d4f-fa6e-427a-981a-2218f66707a7/ec8168ce-2f62-4e9f-9f6f-613363ae6036/frame0.blk (type: video)
```
