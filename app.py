from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from blockchain import Blockchain
from face_auth import face_authenticator
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

import json

# Admin Configuration
ADMIN_PIN = "1234"

# Candidate Persistence Logic
CANDIDATES_FILE = "candidates.json"

def load_candidates():
    if os.path.exists(CANDIDATES_FILE):
        with open(CANDIDATES_FILE, 'r') as f:
            return json.load(f)
    return [] # Return empty list if no file exists

def save_candidates(candidates):
    with open(CANDIDATES_FILE, 'w') as f:
        json.dump(candidates, f, indent=4)

CANDIDATES = load_candidates()
voting_chain = Blockchain()

# Temporary storage for face features during the session
pending_features = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/verify_face', methods=['POST'])
def verify_face():
    data = request.json
    image_data = data.get('image')
    voter_id = data.get('voter_id')

    if not image_data or not voter_id:
        return jsonify({"success": False, "message": "Missing image or Voter ID"}), 400

    success, message, feature_vector = face_authenticator.verify_frame(image_data)
    
    if success:
        session['voter_id'] = voter_id
        session['authenticated'] = True
        # Store feature vector temporarily
        pending_features[voter_id] = feature_vector
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message})

@app.route('/verify_liveness', methods=['POST'])
def verify_liveness():
    data = request.json
    image_data = data.get('image')
    direction = data.get('direction', 'tilt')

    if not image_data:
        return jsonify({"success": False, "message": "Missing image"}), 400

    success, message = face_authenticator.verify_liveness(image_data, direction)
    return jsonify({"success": success, "message": message})

@app.route('/vote')
def vote():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('vote.html', candidates=CANDIDATES, voter_id=session.get('voter_id'))

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    data = request.json
    candidate_id = data.get('candidate_id')
    voter_id = session.get('voter_id')
    
    # Register the voter's features as "voted"
    if voter_id in pending_features:
        face_authenticator.voted_features.append(pending_features[voter_id])
        del pending_features[voter_id]

    success, message = voting_chain.add_vote(voter_id, candidate_id)
    
    if success:
        # Clear session after voting to prevent double voting in the same session
        session.clear()
        return jsonify({"success": True, "message": "Vote cast and secured in blockchain!"})
    else:
        return jsonify({"success": False, "message": message})

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/admin_login')
def admin_login():
    return render_template('admin_login.html')

@app.route('/verify_admin', methods=['POST'])
def verify_admin():
    pin = request.json.get('pin')
    if pin == ADMIN_PIN:
        session['is_admin'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid Admin PIN"})

@app.route('/dashboard')
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    results = voting_chain.get_results()
    chain_data = voting_chain.get_chain_data()
    
    # Format results for Chart.js
    chart_labels = [c['name'] for c in CANDIDATES]
    chart_data = [results.get(c['id'], 0) for c in CANDIDATES]
    
    return render_template('dashboard.html', 
                           chart_labels=chart_labels, 
                           chart_data=chart_data,
                           chain=chain_data)

@app.route('/download_report')
def download_report():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    results = voting_chain.get_results()
    chain_data = voting_chain.get_chain_data()
    
    # Create a bytes buffer for the PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#00f2ff"),
        alignment=1, # Center
        spaceAfter=20
    )
    
    # Title
    elements.append(Paragraph("VOTERP - Election Audit Report", title_style))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Winner Declaration
    if results:
        winner_id = max(results, key=results.get)
        winner_name = "Unknown"
        for c in CANDIDATES:
            if c['id'] == winner_id:
                winner_name = c['name']
                break
        
        elements.append(Paragraph(f"CURRENT ELECTION WINNER: {winner_name}", styles['Heading2']))
        elements.append(Spacer(1, 10))
    
    # Results Table
    elements.append(Paragraph("Vote Distribution", styles['Heading3']))
    data = [["Candidate", "Party", "Votes"]]
    for c in CANDIDATES:
        data.append([c['name'], c['party'], str(results.get(c['id'], 0))])
    
    table = Table(data, colWidths=[200, 150, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a1b26")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 30))
    
    # Blockchain Summary
    elements.append(Paragraph("Blockchain Audit Trail Summary", styles['Heading3']))
    elements.append(Paragraph(f"Total Blocks in Chain: {len(chain_data)}", styles['Normal']))
    if chain_data:
        elements.append(Paragraph(f"Last Block Hash: {chain_data[-1]['hash']}", styles['Normal']))
        elements.append(Paragraph(f"Chain Status: SECURE & IMMUTABLE", styles['Normal']))
    
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("--- End of Official Report ---", styles['Italic']))

    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Election_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype='application/pdf'
    )

@app.route('/api/stats')
def get_stats():
    results = voting_chain.get_results()
    return jsonify({
        "labels": [c['name'] for c in CANDIDATES],
        "values": [results.get(c['id'], 0) for c in CANDIDATES]
    })

@app.route('/reset_election', methods=['POST'])
def reset_election():
    if not session.get('is_admin'):
        return jsonify({"success": False, "message": "Admin access required"}), 403
    
    voting_chain.reset_chain()
    face_authenticator.reset_auth()
    
    # Clear candidates file to remove added candidates
    if os.path.exists(CANDIDATES_FILE):
        os.remove(CANDIDATES_FILE)
    
    # Reset the global CANDIDATES list to empty
    global CANDIDATES
    CANDIDATES = [] 
    
    session.clear()
    return jsonify({"success": True, "message": "Election reset! Everything has been erased. Please add new candidates from the dashboard."})

@app.route('/add_candidate', methods=['POST'])
def add_candidate():
    if not session.get('is_admin'):
        return jsonify({"success": False, "message": "Admin access required"}), 403
    
    data = request.json
    name = data.get('name')
    party = data.get('party', 'Independent')
    
    if not name:
        return jsonify({"success": False, "message": "Candidate name is required"}), 400
    
    new_id = f"cand_{len(CANDIDATES) + 1}"
    new_candidate = {
        "id": new_id,
        "name": name,
        "party": party,
        "image": f"https://api.dicebear.com/7.x/avataaars/svg?seed={name}"
    }
    
    CANDIDATES.append(new_candidate)
    save_candidates(CANDIDATES)
    return jsonify({"success": True, "message": f"Candidate {name} added successfully!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
