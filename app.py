import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from services.summarizer import summarize_text
from googletrans import Translator

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your-secret-key")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

with app.app_context():
    import models
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        text = None
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                # Try different encodings
                encodings = ['utf-8', 'latin-1', 'cp1252']
                for encoding in encodings:
                    try:
                        text = file.read().decode(encoding)
                        break
                    except UnicodeDecodeError:
                        file.seek(0)  # Reset file pointer for next attempt
                        continue

                if text is None:
                    return jsonify({'error': 'Unable to read file. Please ensure it contains valid text.'}), 400
            else:
                return jsonify({'error': 'No file selected'}), 400
        else:
            text = request.form.get('text', '').strip()
            if not text:
                return jsonify({'error': 'No text provided'}), 400

        # Validate text length
        if len(text) > 100000:  # Increased limit to 100k characters
            # Split text into chunks if it's too long
            chunks = [text[i:i+100000] for i in range(0, len(text), 100000)]
            summaries = []

            for chunk in chunks:
                chunk_summary = summarize_text(chunk)
                summaries.append(chunk_summary)

            # Combine summaries
            final_summary = " ".join(summaries)

            # Save to database
            new_summary = models.Summary(
                original_text=text[:100000],  # Store first 100k chars of original text
                summary_text=final_summary
            )
            db.session.add(new_summary)
            db.session.commit()

            return jsonify({'summary': final_summary})

        if len(text) < 10:  # Minimum length check
            return jsonify({'error': 'Text is too short. Please provide more content.'}), 400

        # Language translation
        translator = Translator()
        translated_text = translator.translate(text, dest='en').text

        summary = summarize_text(translated_text)

        # Save to database
        new_summary = models.Summary(
            original_text=text,
            summary_text=summary
        )
        db.session.add(new_summary)
        db.session.commit()

        return jsonify({'summary': summary})
    except Exception as e:
        logger.error(f"Error during summarization: {str(e)}")
        return jsonify({'error': 'An error occurred during summarization. Please try again.'}), 500

@app.route('/summaries', methods=['GET'])
def get_summaries():
    try:
        summaries = models.Summary.query.order_by(models.Summary.created_at.desc()).limit(10).all()
        return jsonify({'summaries': [summary.to_dict() for summary in summaries]})
    except Exception as e:
        logger.error(f"Error fetching summaries: {str(e)}")
        return jsonify({'error': 'An error occurred while fetching summaries'}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)