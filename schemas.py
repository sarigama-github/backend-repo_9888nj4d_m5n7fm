"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date, time

# Example schemas (kept for reference)

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Production tracking schema
class Productionrecord(BaseModel):
    """
    Production records for each entry
    Collection name: "productionrecord" (lowercase of class name)
    """
    date: date = Field(..., description="Production date (local plant date)")
    time: Optional[time] = Field(None, description="Time of the entry (local time)")
    shift: str = Field(..., description="Shift identifier: A (07:00-15:30) or B (15:30-24:00)")
    line: Optional[str] = Field(None, description="Line/Machine/Station identifier")
    product: Optional[str] = Field(None, description="Product or part number")
    operator: Optional[str] = Field(None, description="Operator name or ID")
    count: int = Field(..., ge=0, description="Good units produced")
    defects: Optional[int] = Field(0, ge=0, description="Defective units")
    notes: Optional[str] = Field(None, description="Additional notes")

    # Metadata fields will be added by database helpers: created_at, updated_at

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
