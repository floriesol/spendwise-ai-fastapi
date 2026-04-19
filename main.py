from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import models
from database import engine, get_db


class RegisterRequest(BaseModel):
    username:     str
    email:        str
    password:     str
    first_name:   Optional[str] = ""
    income_type:  Optional[str] = "other"
    income_cycle: Optional[str] = "monthly"


class ExpenseCreate(BaseModel):
    amount:       float
    category_key: str
    description:  Optional[str] = ""
    timestamp:    str


class ExpenseUpdate(BaseModel):
    amount:      Optional[float] = None
    description: Optional[str]  = None


class SavingsGoalCreate(BaseModel):
    name:           str
    target_amount:  float
    current_amount: Optional[float] = 0
    deadline:       Optional[str]   = None