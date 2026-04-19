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

# ── Create tables ─────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SpendWise AI - FastAPI Backend",
    description="Backend API for SpendWise AI mobile and web app",
    version="1.0.0"
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── JWT Config ────────────────────────────────────────────
SECRET_KEY = "spendwise-secret-key-2026"
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 1 day

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ── Pydantic Schemas ──────────────────────────────────────
class RegisterRequest(BaseModel):
    username:     str
    email:        str
    password:     str
    first_name:   Optional[str] = ""
    income_type:  Optional[str] = "other"
    income_cycle: Optional[str] = "monthly"

class ProfileUpdate(BaseModel):
    income_amount: Optional[float] = None
    savings_goal:  Optional[float] = None
    income_type:   Optional[str]   = None 
    income_cycle:  Optional[str]   = None


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

class SavingsGoalUpdate(BaseModel):
    current_amount: Optional[float] = None
    name:           Optional[str]   = None

# ── Helper functions ──────────────────────────────────────
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_token(data: dict):
    to_encode = data.copy()
    expire    = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db)
):
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def seed_categories(db: Session):
    if db.query(models.Category).count() == 0:
        categories = [
            models.Category(key='food',          label='Food & Dining',  icon='🍔', color='#F59E0B'),
            models.Category(key='transport',     label='Transport',       icon='🚗', color='#6366F1'),
            models.Category(key='shopping',      label='Shopping',        icon='🛍️', color='#EC4899'),
            models.Category(key='utilities',     label='Utilities',       icon='💡', color='#2DD4BF'),
            models.Category(key='health',        label='Health',          icon='💊', color='#10B981'),
            models.Category(key='entertainment', label='Entertainment',   icon='🎮', color='#8B5CF6'),
            models.Category(key='savings',       label='Savings',         icon='💰', color='#1A2B47'),
            models.Category(key='education',     label='Education',       icon='📚', color='#3B82F6'),
            models.Category(key='other',         label='Other',           icon='📦', color='#94A3B8'),
        ]
        db.add_all(categories)
        db.commit()

# ── Startup ───────────────────────────────────────────────
@app.on_event("startup")
def startup():
    db = next(get_db())
    seed_categories(db)

# ── Root ──────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "system":  "SpendWise AI",
        "version": "1.0.0",
        "status":  "running",
        "docs":    "http://127.0.0.1:8000/docs",
    }

# ── AUTH ──────────────────────────────────────────────────
@app.post("/auth/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    user = models.User(
        username        = data.username,
        email           = data.email,
        first_name      = data.first_name,
        hashed_password = hash_password(data.password),
        income_type     = data.income_type,
        income_cycle    = data.income_cycle,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    insight = models.MLInsight(user_id=user.id)
    db.add(insight)
    db.commit()

    return {
        "id":         user.id,
        "username":   user.username,
        "email":      user.email,
        "first_name": user.first_name,
    }

@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.username})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":         user.id,
            "username":   user.username,
            "email":      user.email,
            "first_name": user.first_name,
        }
    }

@app.get("/auth/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {
        "id":           current_user.id,
        "username":     current_user.username,
        "email":        current_user.email,
        "first_name":   current_user.first_name,
        "income_type":  current_user.income_type,
        "income_cycle": current_user.income_cycle,
        "income_amount": current_user.income_amount,
        "savings_goal": current_user.savings_goal,
    }
    
# ── CATEGORIES ────────────────────────────────────────────
@app.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return db.query(models.Category).all()

# ── EXPENSES ──────────────────────────────────────────────
@app.get("/expenses")
def get_expenses(
    current_user: models.User = Depends(get_current_user),
    db:           Session     = Depends(get_db)
):
    expenses = db.query(models.Expense).filter(
        models.Expense.user_id == current_user.id
    ).order_by(models.Expense.created_at.desc()).all()

    return [{
        "id":          e.id,
        "amount":      e.amount,
        "description": e.description,
        "timestamp":   e.timestamp,
        "created_at":  e.created_at,
        "updated_at":  e.updated_at,
        "category": {
            "key":   e.category.key   if e.category else None,
            "label": e.category.label if e.category else None,
            "icon":  e.category.icon  if e.category else None,
            "color": e.category.color if e.category else None,
        }
    } for e in expenses]

@app.post("/expenses", status_code=201)
def create_expense(
    data:         ExpenseCreate,
    current_user: models.User = Depends(get_current_user),
    db:           Session     = Depends(get_db)
):
    category = db.query(models.Category).filter(
        models.Category.key == data.category_key
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail=f"Category '{data.category_key}' not found")

    expense = models.Expense(
        amount      = data.amount,
        description = data.description,
        timestamp   = data.timestamp,
        user_id     = current_user.id,
        category_id = category.id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return {
        "id":          expense.id,
        "amount":      expense.amount,
        "description": expense.description,
        "timestamp":   expense.timestamp,
        "category":    {"key": category.key, "label": category.label, "icon": category.icon, "color": category.color},
        "message":     "Expense created successfully"
    }

@app.patch("/expenses/{expense_id}")
def update_expense(
    expense_id:   int,
    data:         ExpenseUpdate,
    current_user: models.User = Depends(get_current_user),
    db:           Session     = Depends(get_db)
):
    expense = db.query(models.Expense).filter(
        models.Expense.id      == expense_id,
        models.Expense.user_id == current_user.id
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if data.amount      is not None: expense.amount      = data.amount
    if data.description is not None: expense.description = data.description
    expense.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(expense)
    return {"id": expense.id, "amount": expense.amount, "description": expense.description, "message": "Updated successfully"}

@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id:   int,
    current_user: models.User = Depends(get_current_user),
    db:           Session     = Depends(get_db)
):
    expense = db.query(models.Expense).filter(
        models.Expense.id      == expense_id,
        models.Expense.user_id == current_user.id
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()