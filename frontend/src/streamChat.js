function dataPayload(frame) {
  // an SSE frame may carry several lines; the payload is the "data: " one
  const line = frame.split('\n').find(l => l.startsWith('data: '))
  return line === undefined ? null : line.slice(6)
}

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

    const parts = buffer.split('\n\n')
    buffer = parts.pop()

    for (const part of parts) {
      const payload = dataPayload(part)
      if (payload === null) continue

      // both token and citation payloads are JSON-encoded, so a token
      // containing newlines can't break SSE framing
      if (part.startsWith('event: citations')) {
        onCitations(JSON.parse(payload))
      } else {
        onToken(JSON.parse(payload))
      }
    }
  }
}
