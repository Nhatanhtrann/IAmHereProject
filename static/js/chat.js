async function sendMessage() {
    const userMessage = document.getElementById('user-input').value;
    const chatbox = document.getElementById('chatbox');
    
    chatbox.innerHTML += `<div>You: ${userMessage}</div>`;
    
    const response = await fetch('https://dialogflow.googleapis.com/v3/projects/YOUR_PROJECT_ID/locations/YOUR_LOCATION/agents/YOUR_AGENT_ID/sessions/YOUR_SESSION_ID:detectIntent', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${YOUR_ACCESS_TOKEN}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            queryInput: {
                text: {
                    text: userMessage,
                    languageCode: 'en'
                }
            }
        })
    });
    
    const jsonResponse = await response.json();
    const botMessage = jsonResponse.queryResult.fulfillmentText;
    
    chatbox.innerHTML += `<div>Bot: ${botMessage}</div>`;
}
