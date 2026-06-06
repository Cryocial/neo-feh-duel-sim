function calculate() {
            const n1 = parseFloat(document.getElementById('num1').value);
            const n2 = parseFloat(document.getElementById('num2').value);

            // Make sure the user actually entered numbers
            if (isNaN(n1) || isNaN(n2)) {
                alert("Please enter valid numbers.");
                return;
            }

            const payload = {
                number1: n1,
                number2: n2
            };

            fetch('http://127.0.0.1:5000/api/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('resultDisplay').innerText = data.answer;
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('resultDisplay').innerText = "Error connecting to backend.";
            });
        }