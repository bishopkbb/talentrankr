import os
import uuid
from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import pandas as pd
import shutil
from pathlib import Path
from typing import List, Dict, Any, Union
import io
import re
import numpy as np

# Initialize FastAPI app
app = FastAPI(
    title="TalentRankr API",
    description="AI-powered candidate ranking system",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create directories if they don't exist
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Configure templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Required columns for the CSV
REQUIRED_COLUMNS = ['Name', 'Skills', 'Education', 'Experience', 'CoverLetter']

# Allowed file extensions
ALLOWED_EXTENSIONS = {".csv", ".pdf", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Configuration for scoring
SCORING_CONFIG = {
    # Skills keywords with their importance weights
    "required_skills": {
        "python": 1.0,
        "data analysis": 1.0, 
        "machine learning": 1.0,
        "sql": 0.8,
        "statistics": 0.8,
        "data science": 1.0,
        "pandas": 0.7,
        "numpy": 0.7,
        "scikit-learn": 0.8,
        "tensorflow": 0.9,
        "pytorch": 0.9,
        "deep learning": 1.0,
        "artificial intelligence": 1.0,
        "ai": 1.0,
        "visualization": 0.6,
        "tableau": 0.6,
        "powerbi": 0.6,
        "excel": 0.5,
        "r programming": 0.8,
        "java": 0.7,
        "javascript": 0.6,
        "cloud": 0.7,
        "aws": 0.7,
        "azure": 0.7,
        "docker": 0.6,
        "git": 0.5,
    },
    
    # Experience scoring ranges
    "experience_ranges": {
        "0-1": 10,
        "2-4": 20, 
        "5+": 30
    },
    
    # Education level scoring
    "education_scores": {
        "phd": 20,
        "doctorate": 20,
        "ph.d": 20,
        "msc": 15,
        "mba": 15,
        "master": 15,
        "masters": 15,
        "m.sc": 15,
        "bsc": 10,
        "bachelor": 10,
        "bachelors": 10,
        "b.sc": 10,
        "ba": 10,
        "b.a": 10,
        "diploma": 5,
        "certificate": 5,
        "hnd": 8,
    },
    
    # Cover letter positive keywords
    "cover_letter_keywords": {
        "leadership": 1.0,
        "innovation": 1.0,
        "teamwork": 0.8,
        "collaboration": 0.8,
        "problem solving": 1.0,
        "creative": 0.8,
        "motivated": 0.7,
        "passionate": 0.8,
        "dedicated": 0.7,
        "results-driven": 1.0,
        "analytical": 0.9,
        "strategic": 0.8,
        "excellent": 0.6,
        "outstanding": 0.8,
        "achieve": 0.7,
        "improve": 0.7,
        "optimize": 0.8,
        "efficient": 0.7,
        "successful": 0.7,
        "expertise": 0.8,
        "professional": 0.6,
        "experienced": 0.7,
        "skilled": 0.7,
        "contribute": 0.7,
        "impact": 0.8,
        "value": 0.6,
        "growth": 0.7,
        "development": 0.7,
        "mentor": 0.8,
        "lead": 0.8,
        "manage": 0.7,
    },
    
    # Scoring weights (must sum to 100%)
    "weights": {
        "skills": 0.40,
        "experience": 0.30,
        "education": 0.20,
        "cover_letter": 0.10
    }
}

def clean_text(text: Union[str, float]) -> str:
    """Clean and normalize text for analysis"""
    if pd.isna(text) or text is None:
        return ""
    return str(text).lower().strip()

def extract_years_experience(experience_text: str) -> float:
    """Extract years of experience from text"""
    if not experience_text:
        return 0.0
    
    # Look for patterns like "3 years", "5+ years", "2-4 years"
    patterns = [
        r'(\d+)\+?\s*years?',
        r'(\d+)\s*yr?s?',
        r'(\d+)-(\d+)\s*years?',
        r'(\d+)\s*to\s*(\d+)\s*years?',
        r'over\s*(\d+)\s*years?',
        r'more than\s*(\d+)\s*years?',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, experience_text)
        if matches:
            if isinstance(matches[0], tuple):
                # Range pattern (e.g., "2-4 years")
                return float(max(matches[0]))
            else:
                # Single number pattern
                return float(matches[0])
    
    # If no pattern found, return 0
    return 0.0

def score_skills(skills_text: str, required_skills: Dict[str, float]) -> float:
    """Score applicant skills based on required keywords"""
    if not skills_text:
        return 0.0
    
    skills_text = clean_text(skills_text)
    total_score = 0.0
    matched_skills = 0
    
    for skill, weight in required_skills.items():
        if skill in skills_text:
            total_score += weight
            matched_skills += 1
    
    # Normalize based on number of total skills and matches
    max_possible = sum(required_skills.values())
    return min((total_score / max_possible) * 40, 40) if max_possible > 0 else 0

def score_experience(experience_text: str, experience_ranges: Dict[str, int]) -> float:
    """Score experience based on years"""
    years = extract_years_experience(clean_text(experience_text))
    
    if years >= 5:
        return experience_ranges["5+"]
    elif years >= 2:
        return experience_ranges["2-4"] 
    elif years >= 0:
        return experience_ranges["0-1"]
    else:
        return 0

def score_education(education_text: str, education_scores: Dict[str, int]) -> float:
    """Score education level"""
    if not education_text:
        return 0
    
    education_text = clean_text(education_text)
    
    # Check for education keywords in order of highest score first
    sorted_education = sorted(education_scores.items(), key=lambda x: x[1], reverse=True)
    
    for edu_keyword, score in sorted_education:
        if edu_keyword in education_text:
            return score
    
    return 0  # No recognized education found

def score_cover_letter(cover_letter_text: str, keywords: Dict[str, float]) -> float:
    """Score cover letter based on positive keywords and sentiment"""
    if not cover_letter_text:
        return 0
    
    cover_letter_text = clean_text(cover_letter_text)
    
    total_score = 0.0
    matched_keywords = 0
    
    for keyword, weight in keywords.items():
        if keyword in cover_letter_text:
            total_score += weight
            matched_keywords += 1
    
    # Basic length bonus (longer, more detailed letters get slight bonus)
    length_bonus = min(len(cover_letter_text) / 1000, 1.0)  # Max 1 point for length
    
    # Combine keyword score with length bonus
    keyword_score = min(total_score / 3, 8.0)  # Scale to max 8 points
    final_score = keyword_score + length_bonus
    
    return min(final_score, 10.0)  # Cap at 10 points

def calculate_applicant_score(row: pd.Series) -> Dict[str, Any]:
    """Calculate comprehensive score for a single applicant"""
    
    # Extract individual component scores
    skills_score = score_skills(row.get('Skills', ''), SCORING_CONFIG['required_skills'])
    experience_score = score_experience(row.get('Experience', ''), SCORING_CONFIG['experience_ranges'])
    education_score = score_education(row.get('Education', ''), SCORING_CONFIG['education_scores'])
    cover_letter_score = score_cover_letter(row.get('CoverLetter', ''), SCORING_CONFIG['cover_letter_keywords'])
    
    # Calculate weighted total score
    total_score = (
        skills_score * SCORING_CONFIG['weights']['skills'] +
        experience_score * SCORING_CONFIG['weights']['experience'] + 
        education_score * SCORING_CONFIG['weights']['education'] +
        cover_letter_score * SCORING_CONFIG['weights']['cover_letter']
    )
    
    return {
        'total_score': round(total_score, 2),
        'skills_score': round(skills_score, 2),
        'experience_score': round(experience_score, 2),
        'education_score': round(education_score, 2),
        'cover_letter_score': round(cover_letter_score, 2),
        'breakdown': {
            'skills_percentage': round((skills_score / 40) * 100, 1) if skills_score > 0 else 0,
            'experience_percentage': round((experience_score / 30) * 100, 1) if experience_score > 0 else 0,
            'education_percentage': round((education_score / 20) * 100, 1) if education_score > 0 else 0,
            'cover_letter_percentage': round((cover_letter_score / 10) * 100, 1) if cover_letter_score > 0 else 0,
        }
    }

def rank_applicants(df: pd.DataFrame) -> pd.DataFrame:
    """Rank all applicants and return sorted DataFrame"""
    
    # Calculate scores for all applicants
    scores_data = []
    for idx, row in df.iterrows():
        score_info = calculate_applicant_score(row)
        scores_data.append(score_info)
    
    # Add score columns to DataFrame
    df['Score'] = [s['total_score'] for s in scores_data]
    df['Skills_Score'] = [s['skills_score'] for s in scores_data] 
    df['Experience_Score'] = [s['experience_score'] for s in scores_data]
    df['Education_Score'] = [s['education_score'] for s in scores_data]
    df['CoverLetter_Score'] = [s['cover_letter_score'] for s in scores_data]
    
    # Add breakdown percentages
    df['Skills_Percentage'] = [s['breakdown']['skills_percentage'] for s in scores_data]
    df['Experience_Percentage'] = [s['breakdown']['experience_percentage'] for s in scores_data]
    df['Education_Percentage'] = [s['breakdown']['education_percentage'] for s in scores_data]
    df['CoverLetter_Percentage'] = [s['breakdown']['cover_letter_percentage'] for s in scores_data]
    
    # Sort by total score (highest first)
    df_ranked = df.sort_values('Score', ascending=False).reset_index(drop=True)
    
    # Add rank column
    df_ranked['Rank'] = range(1, len(df_ranked) + 1)
    
    return df_ranked

def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to specified length with ellipsis"""
    if pd.isna(text):
        return ""
    text_str = str(text)
    return text_str[:max_length] + "..." if len(text_str) > max_length else text_str

def validate_file(file: UploadFile) -> tuple[bool, str]:
    """Validate uploaded file type and size"""
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Only {', '.join(ALLOWED_EXTENSIONS)} files are allowed."
    
    return True, "File is valid"


# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the upload page"""
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/upload-csv", response_class=HTMLResponse)
async def upload_csv(request: Request, file: UploadFile = File(...)):
    """
    Handle CSV upload with applicant data validation and preview
    """
    try:
        # Check if file is CSV
        if not file.filename.lower().endswith('.csv'):
            error_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Invalid File Type - TalentRankr</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-100 min-h-screen">
                <div class="container mx-auto px-4 py-8">
                    <div class="max-w-2xl mx-auto">
                        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                            <div class="flex">
                                <div class="flex-shrink-0">
                                    <svg class="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                                    </svg>
                                </div>
                                <div class="ml-3">
                                    <h3 class="text-sm font-medium text-red-800">Invalid File Type</h3>
                                    <div class="mt-2 text-sm text-red-700">
                                        <p>Please upload a CSV file. The uploaded file "{file.filename}" is not a valid CSV format.</p>
                                    </div>
                                    <div class="mt-4">
                                        <div class="flex space-x-2">
                                            <a href="/" class="bg-red-100 hover:bg-red-200 text-red-800 text-xs font-medium px-3 py-2 rounded transition-colors">
                                                Go Back
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=400)

        # Read the CSV file
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))

        # Validate required columns
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        
        if missing_columns:
            error_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Missing Columns - TalentRankr</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-100 min-h-screen">
                <div class="container mx-auto px-4 py-8">
                    <div class="max-w-4xl mx-auto">
                        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                            <div class="flex">
                                <div class="flex-shrink-0">
                                    <svg class="h-5 w-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                                    </svg>
                                </div>
                                <div class="ml-3 flex-1">
                                    <h3 class="text-sm font-medium text-yellow-800">Missing Required Columns</h3>
                                    <div class="mt-2 text-sm text-yellow-700">
                                        <p>The CSV file is missing the following required columns:</p>
                                        <ul class="mt-2 list-disc list-inside">
                                            {''.join([f'<li><code class="bg-yellow-100 px-1 rounded text-xs">{col}</code></li>' for col in missing_columns])}
                                        </ul>
                                        <div class="mt-4">
                                            <p class="font-medium">Required columns are:</p>
                                            <div class="mt-2 flex flex-wrap gap-2">
                                                {''.join([f'<span class="bg-indigo-100 text-indigo-800 text-xs font-medium px-2 py-1 rounded">{col}</span>' for col in REQUIRED_COLUMNS])}
                                            </div>
                                        </div>
                                        <div class="mt-4">
                                            <p class="font-medium">Found columns in your file:</p>
                                            <div class="mt-2 flex flex-wrap gap-2">
                                                {''.join([f'<span class="bg-gray-100 text-gray-800 text-xs font-medium px-2 py-1 rounded">{col}</span>' for col in df.columns.tolist()])}
                                            </div>
                                        </div>
                                    </div>
                                    <div class="mt-4">
                                        <div class="flex space-x-2">
                                            <a href="/" class="bg-yellow-100 hover:bg-yellow-200 text-yellow-800 text-xs font-medium px-3 py-2 rounded transition-colors">
                                                Upload New File
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=400)

        # Save the file temporarily for later processing
        file_id = str(uuid.uuid4())
        file_path = f"static/uploads/{file_id}.csv"
        
        with open(file_path, "wb") as f:
            f.write(contents)

        # Store candidates in app state for the candidate detail route
        df_ranked = rank_applicants(df)
        if not hasattr(app.state, "candidates"):
            app.state.candidates = []
        app.state.candidates = df_ranked.to_dict('records')
        app.state.current_file_id = file_id

        # Get first 5 rows for preview
        preview_df = df.head(5)
        
        # Prepare preview data with truncated text
        preview_data = []
        for _, row in preview_df.iterrows():
            preview_data.append({
                'Name': truncate_text(row['Name']),
                'Skills': truncate_text(row['Skills']),
                'Education': truncate_text(row['Education']),
                'Experience': truncate_text(row['Experience']),
                'CoverLetter': truncate_text(row['CoverLetter'])
            })

        # Generate HTML preview page (keeping existing inline HTML for preview)
        preview_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CSV Preview - TalentRankr</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        </head>
        <body class="bg-gray-100 min-h-screen">
            <div class="container mx-auto px-4 py-8">
                <!-- Header -->
                <div class="text-center mb-8">
                    <div class="flex items-center justify-center mb-4">
                        <div class="bg-indigo-600 p-2 rounded-xl mr-3">
                            <i class="fas fa-table text-white text-xl"></i>
                        </div>
                        <h1 class="text-3xl font-bold text-gray-900">CSV Preview</h1>
                    </div>
                    <p class="text-gray-600">Review your uploaded applicant data before proceeding to ranking</p>
                </div>

                <!-- File Info -->
                <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
                    <div class="flex items-center justify-between flex-wrap gap-4">
                        <div class="flex items-center">
                            <div class="bg-green-100 rounded-full p-2 mr-3">
                                <i class="fas fa-check text-green-600"></i>
                            </div>
                            <div>
                                <h3 class="font-medium text-gray-900">File Uploaded Successfully</h3>
                                <p class="text-sm text-gray-600">Filename: {file.filename}</p>
                            </div>
                        </div>
                        <div class="text-right">
                            <p class="text-sm text-gray-600">Total Applicants</p>
                            <p class="text-2xl font-bold text-indigo-600">{len(df)}</p>
                        </div>
                    </div>
                </div>

                <!-- Preview Table -->
                <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden mb-6">
                    <div class="px-6 py-4 border-b border-gray-200">
                        <h3 class="text-lg font-medium text-gray-900">Preview (First 5 Applicants)</h3>
                        <p class="text-sm text-gray-600 mt-1">Text longer than 50 characters is truncated for display</p>
                    </div>
                    
                    <div class="overflow-x-auto">
                        <table class="min-w-full divide-y divide-gray-200">
                            <thead class="bg-indigo-600">
                                <tr>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-white uppercase tracking-wider">Name</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-white uppercase tracking-wider">Skills</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-white uppercase tracking-wider">Education</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-white uppercase tracking-wider">Experience</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-white uppercase tracking-wider">Cover Letter</th>
                                </tr>
                            </thead>
                            <tbody class="bg-white divide-y divide-gray-200">
                                {''.join([f'''
                                <tr class="{'bg-gray-50' if i % 2 == 1 else 'bg-white'} hover:bg-indigo-50 transition-colors">
                                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{row['Name'] or 'N/A'}</td>
                                    <td class="px-6 py-4 text-sm text-gray-700">
                                        <div class="max-w-xs">
                                            <p class="truncate" title="{row['Skills']}">{row['Skills'] or 'N/A'}</p>
                                        </div>
                                    </td>
                                    <td class="px-6 py-4 text-sm text-gray-700">
                                        <div class="max-w-xs">
                                            <p class="truncate" title="{row['Education']}">{row['Education'] or 'N/A'}</p>
                                        </div>
                                    </td>
                                    <td class="px-6 py-4 text-sm text-gray-700">
                                        <div class="max-w-xs">
                                            <p class="truncate" title="{row['Experience']}">{row['Experience'] or 'N/A'}</p>
                                        </div>
                                    </td>
                                    <td class="px-6 py-4 text-sm text-gray-700">
                                        <div class="max-w-xs">
                                            <p class="truncate" title="{row['CoverLetter']}">{row['CoverLetter'] or 'N/A'}</p>
                                        </div>
                                    </td>
                                </tr>
                                ''' for i, row in enumerate(preview_data)])}
                            </tbody>
                        </table>
                    </div>
                </div>

                {f'''
                <!-- Show more info if there are more records -->
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <i class="fas fa-info-circle text-blue-600"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm text-blue-800">
                                Showing 5 of {len(df)} applicants. All {len(df)} applicants will be processed during ranking.
                            </p>
                        </div>
                    </div>
                </div>
                ''' if len(df) > 5 else ''}

                <!-- Action Buttons -->
                <div class="flex flex-col sm:flex-row gap-4 justify-center items-center">
                    <a href="/rank/{file_id}" 
                       class="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-8 rounded-lg shadow-lg transform transition-all duration-200 hover:scale-105 hover:shadow-xl flex items-center">
                        <i class="fas fa-chart-line mr-2"></i>
                        Proceed to Ranking
                    </a>
                    <a href="/" 
                       class="bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium py-3 px-8 rounded-lg transition-colors flex items-center">
                        <i class="fas fa-upload mr-2"></i>
                        Upload New File
                    </a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=preview_html, status_code=200)

    except pd.errors.EmptyDataError:
        error_html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Empty File - TalentRankr</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-100 min-h-screen">
            <div class="container mx-auto px-4 py-8">
                <div class="max-w-2xl mx-auto">
                    <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                        <div class="flex">
                            <div class="flex-shrink-0">
                                <svg class="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                                </svg>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-sm font-medium text-red-800">Empty CSV File</h3>
                                <div class="mt-2 text-sm text-red-700">
                                    <p>The uploaded CSV file appears to be empty or contains no data.</p>
                                </div>
                                <div class="mt-4">
                                    <a href="/" class="bg-red-100 hover:bg-red-200 text-red-800 text-xs font-medium px-3 py-2 rounded transition-colors">
                                        Upload New File
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

    except Exception as e:
        error_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Processing Error - TalentRankr</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-100 min-h-screen">
            <div class="container mx-auto px-4 py-8">
                <div class="max-w-2xl mx-auto">
                    <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                        <div class="flex">
                            <div class="flex-shrink-0">
                                <svg class="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                                </svg>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-sm font-medium text-red-800">File Processing Error</h3>
                                <div class="mt-2 text-sm text-red-700">
                                    <p>An error occurred while processing your file: {str(e)}</p>
                                    <p class="mt-2">Please ensure your CSV file is properly formatted with UTF-8 encoding.</p>
                                </div>
                                <div class="mt-4">
                                    <a href="/" class="bg-red-100 hover:bg-red-200 text-red-800 text-xs font-medium px-3 py-2 rounded transition-colors">
                                        Try Again
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

@app.get("/rank/{file_id}")
async def rank_applicants_html(request: Request, file_id: str):
    """Display ranked applicants using template"""
    try:
        # Load the CSV file
        file_path = f"static/uploads/{file_id}.csv"
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        df = pd.read_csv(file_path)
        df_ranked = rank_applicants(df)
        
        # Store candidates in app state for candidate detail route
        app.state.candidates = df_ranked.to_dict('records')
        app.state.current_file_id = file_id
        
        # Prepare data for template
        applicants_data = []
        for _, row in df_ranked.iterrows():
            applicant = {
                'rank': row['Rank'],
                'name': row['Name'],
                'total_score': row['Score'],
                'skills_score': row['Skills_Score'],
                'experience_score': row['Experience_Score'], 
                'education_score': row['Education_Score'],
                'cover_letter_score': row['CoverLetter_Score'],
                'skills_percentage': row['Skills_Percentage'],
                'experience_percentage': row['Experience_Percentage'],
                'education_percentage': row['Education_Percentage'],
                'cover_letter_percentage': row['CoverLetter_Percentage'],
            }
            applicants_data.append(applicant)
        
        # Calculate summary stats
        total_applicants = len(df_ranked)
        high_performers_count = len([a for a in applicants_data if a['total_score'] >= 70])
        average_score = round(df_ranked['Score'].mean(), 1)
        top_score = round(df_ranked['Score'].max(), 1)
        
        return templates.TemplateResponse("ranked.html", {
            "request": request,
            "file_id": file_id,
            "ranked_applicants": applicants_data,
            "total_applicants": total_applicants,
            "high_performers_count": high_performers_count,
            "average_score": average_score,
            "top_score": top_score
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")

@app.get("/candidate/{id}")
async def candidate_detail(request: Request, id: int):
    """Display individual candidate details"""
    if not hasattr(app.state, "candidates") or id < 1 or id > len(app.state.candidates):
        return RedirectResponse(url="/", status_code=303)
    
    candidate = app.state.candidates[id - 1]
    file_id = getattr(app.state, 'current_file_id', '')
    
    return templates.TemplateResponse("candidate.html", {
        "request": request, 
        "candidate": candidate, 
        "id": id,
        "file_id": file_id,
        "total_candidates": len(app.state.candidates)
    })

@app.get("/api/rank/{file_id}")
async def rank_applicants_json(file_id: str):
    """Return ranked applicants in JSON format"""
    try:
        # Load the CSV file
        file_path = f"static/uploads/{file_id}.csv"
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        df = pd.read_csv(file_path)
        
        # Rank applicants
        df_ranked = rank_applicants(df)
        
        # Convert to JSON-friendly format
        results = {
            "success": True,
            "total_applicants": len(df_ranked),
            "average_score": round(df_ranked['Score'].mean(), 2),
            "top_score": round(df_ranked['Score'].max(), 2),
            "scoring_methodology": {
                "skills_weight": "40%",
                "experience_weight": "30%", 
                "education_weight": "20%",
                "cover_letter_weight": "10%"
            },
            "ranked_applicants": []
        }
        
        for _, row in df_ranked.iterrows():
            applicant = {
                "rank": int(row['Rank']),
                "name": row['Name'],
                "total_score": row['Score'],
                "score_breakdown": {
                    "skills": {
                        "score": row['Skills_Score'],
                        "percentage": row['Skills_Percentage'],
                        "max_possible": 40
                    },
                    "experience": {
                        "score": row['Experience_Score'], 
                        "percentage": row['Experience_Percentage'],
                        "max_possible": 30
                    },
                    "education": {
                        "score": row['Education_Score'],
                        "percentage": row['Education_Percentage'], 
                        "max_possible": 20
                    },
                    "cover_letter": {
                        "score": row['CoverLetter_Score'],
                        "percentage": row['CoverLetter_Percentage'],
                        "max_possible": 10
                    }
                },
                "applicant_data": {
                    "skills": row['Skills'],
                    "education": row['Education'],
                    "experience": row['Experience'], 
                    "cover_letter": row['CoverLetter']
                }
            }
            results["ranked_applicants"].append(applicant)
        
        return JSONResponse(content=results)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")

@app.get("/api/rank")
async def api_rank_current():
    """Return currently ranked candidates in JSON format"""
    if not hasattr(app.state, "candidates") or not app.state.candidates:
        return JSONResponse(content={
            "success": False,
            "message": "No candidates ranked yet. Please upload a file first."
        })
    
    # Reshape data for API
    api_candidates = []
    for idx, candidate in enumerate(app.state.candidates):
        api_candidate = {
            "id": idx + 1,
            "rank": candidate.get("Rank", idx + 1),
            "name": candidate.get("Name", ""),
            "score": candidate.get("Score", 0),
            "skills": candidate.get("Skills", ""),
            "education": candidate.get("Education", ""),
            "experience": candidate.get("Experience", ""),
            "cover_letter": candidate.get("CoverLetter", ""),
            "score_breakdown": {
                "skills_score": candidate.get("Skills_Score", 0),
                "experience_score": candidate.get("Experience_Score", 0),
                "education_score": candidate.get("Education_Score", 0),
                "cover_letter_score": candidate.get("CoverLetter_Score", 0)
            }
        }
        api_candidates.append(api_candidate)
    
    return JSONResponse(content={
        "success": True,
        "candidates": api_candidates,
        "total_count": len(api_candidates)
    })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "TalentRankr API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)