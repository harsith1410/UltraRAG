export async function streamChat(subjectId, message, model, onToken, onCitations) {
  const response = await fetch(`http://127.0.0.1:8000/chat/${subjectId}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message, model })
})

const reader = response.body.getReader()
const decoder = new TextDecoder()
let buffer = ''

while (true) {
  const { value, done } = await reader.read()
  if (done) break

  buffer += decoder.decode(value, { stream: true })

  let parts = buffer.split('\n\n')
  buffer = parts.pop()

  for (const part of parts) {
    if (part.startsWith('event: citations')) {
      const jsonLine = part.split('\n').find(line => line.startsWith('data: '))
      onCitations(JSON.parse(jsonLine.replace('data: ', '')))
    } else if (part.startsWith('data: ')) {
      onToken(part.replace('data: ', ''))
    }
  }
}
}