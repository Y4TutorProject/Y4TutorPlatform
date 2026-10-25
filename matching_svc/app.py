from vector_search import vector_search
from flask import Flask, jsonify, request


app = Flask(__name__)


@app.route('/get-recommendations', methods=['GET'])
def get_recommendations():
    """
    Endpoint to get tutor recommendations based on a student's vector.

    Example request body:
    {
        "student_vector": [5, 4, 2, 5, 5],
        "tutors": {
            "user1": [4, 5, 2, 4, 5],
            "user2": [1, 1, 5, 2, 1],
            "user3": [5, 3, 3, 5, 4]
        }
    }
    Example response body:
    [
        {"tutor_id": "user1", "similarity": 0.9959940002745983},
        {"tutor_id": "user3", "similarity": 0.9876543210987654}
    ]
    """
    data = request.get_json()
    try:
        student_vector = data.get('student_vector')
        if student_vector is None:
            return jsonify({'error': 'Missing student_vector in request body'}), 400
        if not isinstance(student_vector, list):
            return jsonify({'error': 'student_vector must be a list'}), 400
        
        tutors= data.get('tutors')
        if tutors is None:
            return jsonify({'error': 'Missing tutors in request body'}), 400
        if not isinstance(tutors, dict):
            return jsonify({'error': 'tutors must be a dictionary'}), 400
        if not all(isinstance(v, list) for v in tutors.values()):
            return jsonify({'error': 'All tutor values must be lists'}), 400
        if any(len(v) != len(student_vector) for v in tutors.values()):
            return jsonify({'error': 'All tutor vectors must match student_vector length'}), 400
        result = vector_search(student_vector,tutors, list(tutors.keys()), top_k=len(tutors))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    return jsonify({'status': 'ready'}), 200

app.run(host='0.0.0.0', port=5000, debug=True)
