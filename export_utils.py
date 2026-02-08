"""
CSV export utilities for admin commands.
"""
import csv
import io
from datetime import datetime
from typing import Optional

import db


def generate_orders_csv(status: Optional[str] = None) -> tuple[str, bytes]:
    """
    Generate CSV file content from orders.
    
    Args:
        status: Optional status filter (new/accepted/contacted/done)
        
    Returns:
        Tuple of (filename, csv_bytes)
    """
    # Get orders from database
    orders = db.export_orders(status)
    
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if status:
        filename = f"orders_{status}_{timestamp}.csv"
    else:
        filename = f"orders_{timestamp}.csv"
    
    # Create CSV in memory
    output = io.StringIO()
    
    # Define columns
    columns = [
        "id", "user_id", "username", "service", "name", 
        "phone", "date_text", "details", "status", 
        "created_at", "updated_at"
    ]
    
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    
    for order in orders:
        writer.writerow(order)
    
    # Get CSV content as bytes (UTF-8 with BOM for Excel compatibility)
    csv_content = output.getvalue()
    csv_bytes = ("\ufeff" + csv_content).encode("utf-8")
    
    return filename, csv_bytes
