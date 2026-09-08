import { useEffect, useRef, useState } from 'react'
import { streamChat } from "./streamChat.js";
import './index.css'

function App() {
  const [subjects, setSubjects] = useState([])
  const [selectedSubject, setSelectedSubject] = useState("")
  const [inputValue, setInputValue] = useState('')
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [file, setFile] = useState('')
  const [isDark, setIsDark] = useState(true)
  const [documents, setDocuments] = useState([])
  const [selectedDocIds, setSelectedDocIds] = useState([])
  const [isGeneratingNotes, setIsGeneratingNotes] = useState(false)
  const [notesResult, setNotesResult] = useState(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState(null)
  const [isGeneratingCards, setIsGeneratingCards] = useState(false)
  const [cardsResult, setCardsResult] = useState(null)
  const [deckName, setDeckName] = useState('')
  const [ankiAvailable, setAnkiAvailable] = useState(null)
  const [pushMessage, setPushMessage] = useState(null)
  const [urlValue, setUrlValue] = useState('')
  const [isIngestingUrl, setIsIngestingUrl] = useState(false)
  const [uploadMessage, setUploadMessage] = useState(null)
  const [formats, setFormats] = useState([])
  const [duplicateWarning, setDuplicateWarning] = useState(null)
  const [events, setEvents] = useState([])
  const [showCalendar, setShowCalendar] = useState(false)
  const [eventForm, setEventForm] = useState({ summary: '', start: '', end: '' })
  const [calendarMessage, setCalendarMessage] = useState(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/subject/')
      .then(res => res.json())
      .then(data => setSubjects(data.Subjects))
      .catch(err => console.error('Fetch failed:', err))
  }, [])

  function fetchDocuments(subjectId) {
    if (!subjectId) {
      setDocuments([])
      setSelectedDocIds([])
      return
    }
    fetch(`http://127.0.0.1:8000/subject/${subjectId}/documents`)
      .then(res => res.json())
      .then(data => setDocuments(data.Documents))
      .catch(err => console.error('Fetch failed:', err))
  }

  useEffect(() => {
    fetchDocuments(selectedSubject)
  }, [selectedSubject])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  useEffect(() => {
    fetch('http://127.0.0.1:8000/anki/status')
      .then(res => res.json())
      .then(data => setAnkiAvailable(data.available))
      .catch(() => setAnkiAvailable(false))
  }, [])

  useEffect(() => {
    fetch('http://127.0.0.1:8000/formats')
      .then(res => res.json())
      .then(data => setFormats(data.extensions))
      .catch(() => setFormats([]))
  }, [])

  function fetchEvents() {
    fetch('http://127.0.0.1:8000/calendar/events?days=14')
      .then(res => res.json())
      .then(data => setEvents(data.events || []))
      .catch(err => console.error('Calendar fetch failed:', err))
  }

  async function handleCreateEvent() {
    if (!eventForm.summary.trim() || !eventForm.start) {
      setCalendarMessage('Give the event a title and a start time')
      return
    }

    try {
      const res = await fetch('http://127.0.0.1:8000/calendar/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: eventForm.summary.trim(),
          start: eventForm.start,
          end: eventForm.end || null,
        })
      })
      const data = await res.json()
      if (!res.ok) {
        setCalendarMessage(data.detail || 'Could not create event')
        return
      }
      setCalendarMessage(`Added "${data.event.summary}"`)
      setEventForm({ summary: '', start: '', end: '' })
      fetchEvents()
    } catch (err) {
      console.error('Event creation failed:', err)
      setCalendarMessage('Could not create event')
    }
  }

  function formatEventTime(event) {
    if (event.all_day) return new Date(event.start).toLocaleDateString()
    return new Date(event.start).toLocaleString([], {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
    })
  }

  function ingestSummary(data) {
    const figures = data.figures ? `, ${data.figures} figure(s)` : ''
    return `Ingested ${displayName(data.filename)} — ${data.chunks} chunk(s)${figures}`
  }

  function flashUpload(message) {
    setUploadMessage(message)
    setTimeout(() => setUploadMessage(null), 5000)
  }

  function toggleDoc(id) {
    setSelectedDocIds(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    )
  }

  function displayName(filename) {
    const parts = filename.split('_')
    return parts.length > 1 ? parts.slice(1).join('_') : filename
  }

  async function handleSend() {
    if (isStreaming || !inputValue.trim()) return
    setIsStreaming(true)
    const userMessage = { role: 'user', content: inputValue }
    const assistantMessage = { role: 'assistant', content: '', citations: null }

    setMessages(prev => [...prev, userMessage, assistantMessage])
    setInputValue('')

    try {
      await streamChat(
        selectedSubject,
        inputValue,
        "openai/gpt-oss-120b",
        (token) => {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = { ...last, content: last.content + token }
            return updated
          })
        },
        (citations) => {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = { ...last, citations }
            return updated
          })
        }
      )
    } catch (err) {
      console.error('Chat stream failed:', err)
    } finally {
      setIsStreaming(false)
    }
  }

  async function handleUpload(force = false) {
    if (!file || !selectedSubject) {
      flashUpload('Pick a subject and a file first')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('subject_id', selectedSubject)
    formData.append('force', force)

    setDuplicateWarning(null)

    try {
      const response = await fetch('http://127.0.0.1:8000/upload', {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()
      if (!response.ok) {
        if (data.detail?.reason === 'near_duplicate') {
          setDuplicateWarning({ ...data.detail, retry: () => handleUpload(true) })
          return
        }
        flashUpload(typeof data.detail === 'string' ? data.detail : 'Upload failed')
        return
      }
      flashUpload(ingestSummary(data))
      fetchDocuments(selectedSubject)
    } catch (err) {
      console.error('Upload failed:', err)
      flashUpload('Upload failed')
    }
  }

  async function handleIngestUrl(force = false) {
    if (!urlValue.trim() || !selectedSubject || isIngestingUrl) {
      if (!selectedSubject) flashUpload('Pick a subject first')
      return
    }
    setIsIngestingUrl(true)
    setDuplicateWarning(null)

    try {
      const res = await fetch('http://127.0.0.1:8000/ingest/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlValue.trim(), subject_id: Number(selectedSubject), force })
      })
      const data = await res.json()
      if (!res.ok) {
        if (data.detail?.reason === 'near_duplicate') {
          setDuplicateWarning({ ...data.detail, retry: () => handleIngestUrl(true) })
          return
        }
        flashUpload(typeof data.detail === 'string' ? data.detail : 'URL ingest failed')
        return
      }
      flashUpload(ingestSummary(data))
      setUrlValue('')
      fetchDocuments(selectedSubject)
    } catch (err) {
      console.error('URL ingest failed:', err)
      flashUpload('URL ingest failed')
    } finally {
      setIsIngestingUrl(false)
    }
  }

  async function handleDeleteSubject(id) {
    const confirmed = window.confirm("Delete this subject and all its documents?")
    if (!confirmed) return

    const res = await fetch(`http://127.0.0.1:8000/subject/${id}`, {
      method: 'DELETE',
    })

    if (res.ok) {
      setSubjects(prev => prev.filter(s => s.id !== Number(id)))
      if (String(selectedSubject) === String(id)) {
        setSelectedSubject("")
      }
    } else {
      console.error("Delete failed")
    }
  }

  async function handleGenerateNotes() {
    if (selectedDocIds.length === 0 || isGeneratingNotes) return
    setIsGeneratingNotes(true)
    setNotesResult(null)

    try {
      const res = await fetch('http://127.0.0.1:8000/notes/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_ids: selectedDocIds })
      })
      const data = await res.json()
      setNotesResult(data.notes)
    } catch (err) {
      console.error('Notes generation failed:', err)
    } finally {
      setIsGeneratingNotes(false)
    }
  }

  function copyNotes() {
    if (notesResult) navigator.clipboard.writeText(notesResult)
  }

  function downloadNotes() {
    if (!notesResult) return
    const blob = new Blob([notesResult], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'notes.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleGenerateFlashcards() {
    if (selectedDocIds.length === 0 || isGeneratingCards) return
    setIsGeneratingCards(true)
    setCardsResult(null)
    setPushMessage(null)

    try {
      const res = await fetch('http://127.0.0.1:8000/flashcards/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_ids: selectedDocIds, count: 25 })
      })
      if (!res.ok) {
        const err = await res.json()
        setPushMessage(err.detail || 'Flashcard generation failed')
        return
      }
      const data = await res.json()
      setCardsResult(data)
      setDeckName(data.deck)
    } catch (err) {
      console.error('Flashcard generation failed:', err)
      setPushMessage('Flashcard generation failed')
    } finally {
      setIsGeneratingCards(false)
    }
  }

  function removeCard(index) {
    setCardsResult(prev => ({
      ...prev,
      cards: prev.cards.filter((_, i) => i !== index)
    }))
  }

  async function handlePushToAnki() {
    if (!cardsResult || cardsResult.cards.length === 0) return
    setPushMessage('Pushing...')

    try {
      const res = await fetch('http://127.0.0.1:8000/flashcards/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cards: cardsResult.cards,
          deck: deckName,
          tags: [cardsResult.subject.toLowerCase()]
        })
      })
      const data = await res.json()
      if (!res.ok) {
        setPushMessage(data.detail || 'Push failed')
        setAnkiAvailable(false)
        return
      }
      setAnkiAvailable(true)
      setPushMessage(`Added ${data.added} card(s) to "${data.deck}"` + (data.skipped ? ` — ${data.skipped} duplicate(s) skipped` : ''))
    } catch (err) {
      console.error('Push to Anki failed:', err)
      setPushMessage('Push failed')
    }
  }

  async function downloadFlashcards() {
    if (!cardsResult) return
    const res = await fetch('http://127.0.0.1:8000/flashcards/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cards: cardsResult.cards,
        deck: deckName,
        tags: [cardsResult.subject.toLowerCase()]
      })
    })
    const data = await res.json()
    const blob = new Blob([data.tsv], { type: 'text/tab-separated-values' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${deckName.replace(/::/g, '_')}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleSyncDrive() {
    if (!selectedSubject || isSyncing) return
    setIsSyncing(true)
    setSyncMessage(null)

    try {
      const res = await fetch(`http://127.0.0.1:8000/drive/sync/${selectedSubject}`, {
        method: 'POST',
      })
      const data = await res.json()
      const count = data.synced ? data.synced.length : 0
      setSyncMessage(count > 0 ? `Synced ${count} new file(s)` : 'No new files')
      fetchDocuments(selectedSubject)
    } catch (err) {
      console.error('Drive sync failed:', err)
      setSyncMessage('Sync failed')
    } finally {
      setIsSyncing(false)
      setTimeout(() => setSyncMessage(null), 4000)
    }
  }

  return (
    <div className={`min-h-screen flex justify-center py-8 px-4 gap-4 transition-colors ${
      isDark ? 'bg-neutral-900' : 'bg-slate-50'
    }`}>

      {/* Left sidebar */}
      <div className={`w-72 shrink-0 h-[85vh] rounded-2xl shadow-md border overflow-y-auto p-4 flex flex-col gap-4 transition-colors ${
        isDark ? 'bg-neutral-800 border-neutral-700' : 'bg-white border-slate-200'
      }`}>

        <div className="flex flex-col gap-2">
          <label className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
            Subject
          </label>
          <div className="flex items-center gap-2">
            <select
              value={selectedSubject}
              onChange={(e) => setSelectedSubject(e.target.value)}
              className={`flex-1 border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
                isDark ? 'bg-neutral-700 border-neutral-600 text-neutral-100' : 'bg-white border-slate-300 text-slate-900'
              }`}
            >
              <option value="">-- choose --</option>
              {subjects.map(subject => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
            <button
              onClick={() => handleDeleteSubject(selectedSubject)}
              disabled={!selectedSubject}
              className={`text-sm px-3 py-1.5 rounded-lg text-white transition ${
                isDark
                  ? 'bg-red-600 hover:bg-red-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                  : 'bg-red-500 hover:bg-red-600 disabled:bg-slate-200 disabled:text-slate-400'
              }`}
            >
              Delete
            </button>
          </div>
        </div>

        <button
          onClick={() => setIsDark(prev => !prev)}
          className={`text-sm px-3 py-1.5 rounded-lg transition self-start ${
            isDark
              ? 'bg-neutral-700 text-yellow-300 hover:bg-neutral-600'
              : 'bg-slate-700 text-white hover:bg-slate-800'
          }`}
        >
          {isDark ? '☀️ Light' : '🌙 Dark'}
        </button>

        <form
          onSubmit={(e) => { e.preventDefault(); handleUpload(false); }}
          className="flex flex-col gap-2"
        >
          <label className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
            Upload
          </label>
          <input
            type="file"
            accept={formats.join(',')}
            onChange={(e) => setFile(e.target.files[0])}
            className={`text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm transition-colors ${
              isDark
                ? 'text-neutral-400 file:bg-neutral-700 file:text-blue-300 hover:file:bg-neutral-600'
                : 'text-slate-500 file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100'
            }`}
          />
          <button
            type="submit"
            className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
              isDark ? 'bg-neutral-600 hover:bg-neutral-500' : 'bg-slate-700 hover:bg-slate-800'
            }`}
          >
            Submit
          </button>
          {formats.length > 0 && (
            <p className={`text-xs ${isDark ? 'text-neutral-500' : 'text-slate-400'}`}>
              {formats.join(' ')}
            </p>
          )}
        </form>

        <div className="flex flex-col gap-2">
          <label className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
            Ingest URL
          </label>
          <input
            value={urlValue}
            onChange={(e) => setUrlValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleIngestUrl(false) }}
            placeholder="https://..."
            className={`border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
              isDark
                ? 'bg-neutral-700 border-neutral-600 text-neutral-100 placeholder-neutral-500'
                : 'bg-white border-slate-300 text-slate-900'
            }`}
          />
          <button
            onClick={() => handleIngestUrl(false)}
            disabled={!urlValue.trim() || !selectedSubject || isIngestingUrl}
            className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
              isDark
                ? 'bg-sky-600 hover:bg-sky-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                : 'bg-sky-600 hover:bg-sky-700 disabled:bg-slate-200 disabled:text-slate-400'
            }`}
          >
            {isIngestingUrl ? 'Fetching...' : 'Fetch & Ingest'}
          </button>
        </div>

        {uploadMessage && (
          <p className={`text-xs ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>
            {uploadMessage}
          </p>
        )}

        {duplicateWarning && (
          <div className={`rounded-lg border p-3 flex flex-col gap-2 ${
            isDark ? 'border-amber-700/60 bg-amber-950/30' : 'border-amber-300 bg-amber-50'
          }`}>
            <p className={`text-xs font-medium ${isDark ? 'text-amber-300' : 'text-amber-800'}`}>
              Looks like a duplicate
            </p>
            <p className={`text-xs ${isDark ? 'text-neutral-400' : 'text-slate-600'}`}>
              {duplicateWarning.matched} of {duplicateWarning.sampled} sampled chunks match{' '}
              <span className="font-medium">{displayName(duplicateWarning.similar_to)}</span>{' '}
              ({Math.round(duplicateWarning.similarity * 100)}% similar).
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => duplicateWarning.retry()}
                className="text-xs px-2 py-1 rounded-lg text-white bg-amber-600 hover:bg-amber-700 transition"
              >
                Ingest anyway
              </button>
              <button
                onClick={() => setDuplicateWarning(null)}
                className={`text-xs px-2 py-1 rounded-lg transition ${
                  isDark ? 'text-neutral-400 hover:bg-neutral-700' : 'text-slate-500 hover:bg-slate-200'
                }`}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <label className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
            Google Drive
          </label>
          <button
            onClick={handleSyncDrive}
            disabled={!selectedSubject || isSyncing}
            className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
              isDark
                ? 'bg-emerald-600 hover:bg-emerald-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                : 'bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400'
            }`}
          >
            {isSyncing ? 'Syncing...' : 'Sync Drive'}
          </button>
          {syncMessage && (
            <p className={`text-xs ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>
              {syncMessage}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => {
              const opening = !showCalendar
              setShowCalendar(opening)
              if (opening) fetchEvents()
            }}
            className={`text-sm font-medium text-left ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}
          >
            Calendar {showCalendar ? '▾' : '▸'}
          </button>

          {showCalendar && (
            <div className="flex flex-col gap-2">
              {events.length === 0 ? (
                <p className={`text-xs ${isDark ? 'text-neutral-500' : 'text-slate-400'}`}>
                  Nothing in the next 14 days
                </p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {events.map(event => (
                    <li key={event.id} className={`text-xs ${isDark ? 'text-neutral-300' : 'text-slate-700'}`}>
                      <span className={isDark ? 'text-neutral-500' : 'text-slate-400'}>
                        {formatEventTime(event)}
                      </span>{' '}
                      {event.link ? (
                        <a href={event.link} target="_blank" rel="noreferrer" className="hover:underline">
                          {event.summary}
                        </a>
                      ) : event.summary}
                    </li>
                  ))}
                </ul>
              )}

              <input
                value={eventForm.summary}
                onChange={(e) => setEventForm(prev => ({ ...prev, summary: e.target.value }))}
                placeholder="New event title"
                className={`border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
                  isDark
                    ? 'bg-neutral-700 border-neutral-600 text-neutral-100 placeholder-neutral-500'
                    : 'bg-white border-slate-300 text-slate-900'
                }`}
              />
              <label className={`text-xs ${isDark ? 'text-neutral-500' : 'text-slate-400'}`}>Starts</label>
              <input
                type="datetime-local"
                value={eventForm.start}
                onChange={(e) => setEventForm(prev => ({ ...prev, start: e.target.value }))}
                className={`border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
                  isDark ? 'bg-neutral-700 border-neutral-600 text-neutral-100' : 'bg-white border-slate-300 text-slate-900'
                }`}
              />
              <label className={`text-xs ${isDark ? 'text-neutral-500' : 'text-slate-400'}`}>Ends (optional)</label>
              <input
                type="datetime-local"
                value={eventForm.end}
                onChange={(e) => setEventForm(prev => ({ ...prev, end: e.target.value }))}
                className={`border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
                  isDark ? 'bg-neutral-700 border-neutral-600 text-neutral-100' : 'bg-white border-slate-300 text-slate-900'
                }`}
              />
              <button
                onClick={handleCreateEvent}
                disabled={!eventForm.summary.trim() || !eventForm.start}
                className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
                  isDark
                    ? 'bg-indigo-600 hover:bg-indigo-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                    : 'bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400'
                }`}
              >
                Add event
              </button>
              {calendarMessage && (
                <p className={`text-xs ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>
                  {calendarMessage}
                </p>
              )}
            </div>
          )}
        </div>

        {documents.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
              Select documents for notes
            </p>
            {documents.map(doc => (
              <label
                key={doc.id}
                className={`flex items-center gap-2 text-sm ${isDark ? 'text-neutral-200' : 'text-slate-700'}`}
              >
                <input
                  type="checkbox"
                  checked={selectedDocIds.includes(doc.id)}
                  onChange={() => toggleDoc(doc.id)}
                />
                {displayName(doc.filename)}
              </label>
            ))}
            <button
              onClick={handleGenerateNotes}
              disabled={selectedDocIds.length === 0 || isGeneratingNotes}
              className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
                isDark
                  ? 'bg-purple-600 hover:bg-purple-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                  : 'bg-purple-600 hover:bg-purple-700 disabled:bg-slate-200 disabled:text-slate-400'
              }`}
            >
              {isGeneratingNotes ? 'Generating...' : 'Create Notes'}
            </button>
            <button
              onClick={handleGenerateFlashcards}
              disabled={selectedDocIds.length === 0 || isGeneratingCards}
              className={`text-sm px-3 py-1.5 rounded-lg text-white transition self-start ${
                isDark
                  ? 'bg-amber-600 hover:bg-amber-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                  : 'bg-amber-600 hover:bg-amber-700 disabled:bg-slate-200 disabled:text-slate-400'
              }`}
            >
              {isGeneratingCards ? 'Generating...' : 'Create Flashcards'}
            </button>
            {ankiAvailable === false && (
              <p className={`text-xs ${isDark ? 'text-neutral-500' : 'text-slate-400'}`}>
                Anki not detected — cards can still be downloaded
              </p>
            )}
          </div>
        )}
      </div>

      {/* Chat panel */}
      <div className={`w-full max-w-2xl flex flex-col h-[85vh] rounded-2xl shadow-md border overflow-hidden transition-colors ${
        isDark ? 'bg-neutral-800 border-neutral-700' : 'bg-white border-slate-200'
      }`}>

        {/* Messages */}
        <div className={`flex-1 overflow-y-auto p-4 flex flex-col gap-3 transition-colors ${
          isDark ? 'bg-neutral-800' : 'bg-white'
        }`}>
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white rounded-br-sm'
                    : 'bg-green-500 text-white rounded-bl-sm'
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>
                {msg.citations?.sources?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/30 text-xs opacity-80">
                    Sources: {msg.citations.sources.map(displayName).join(', ')}
                  </div>
                )}
                {msg.citations?.figures?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/30 flex flex-col gap-2">
                    <p className="text-xs opacity-80">Figures</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.citations.figures.map((figure, f) => (
                        <a
                          key={f}
                          href={`http://127.0.0.1:8000${figure.url}`}
                          target="_blank"
                          rel="noreferrer"
                          title={`${displayName(figure.source)} — page ${figure.page}`}
                        >
                          <img
                            src={`http://127.0.0.1:8000${figure.url}`}
                            alt={`Figure from ${displayName(figure.source)} page ${figure.page}`}
                            className="h-20 w-auto rounded border border-white/40 bg-white object-contain"
                          />
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className={`border-t p-3 flex items-center gap-2 transition-colors ${
          isDark ? 'border-neutral-700 bg-neutral-800' : 'border-slate-200 bg-slate-50'
        }`}>
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !isStreaming) handleSend() }}
            disabled={isStreaming}
            placeholder={isStreaming ? "Waiting for response..." : "Ask a question..."}
            className={`flex-1 border rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
              isDark
                ? 'bg-neutral-700 border-neutral-600 text-neutral-100 placeholder-neutral-400 disabled:bg-neutral-800 disabled:text-neutral-600'
                : 'bg-white border-slate-300 text-slate-900 disabled:bg-slate-100 disabled:text-slate-400'
            }`}
          />
          <button
            disabled={isStreaming}
            onClick={handleSend}
            className={`px-4 py-2 rounded-full text-white text-sm font-medium transition ${
              isDark
                ? 'bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-700 disabled:text-neutral-500 disabled:cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed'
            }`}
          >
            Send
          </button>
        </div>

      </div>

      {/* Notes modal */}
      {notesResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-2xl max-h-[85vh] rounded-2xl shadow-xl border flex flex-col overflow-hidden ${
            isDark ? 'bg-neutral-800 border-neutral-700' : 'bg-white border-slate-200'
          }`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-neutral-700' : 'border-slate-200'}`}>
              <h2 className={`text-sm font-semibold ${isDark ? 'text-neutral-200' : 'text-slate-800'}`}>Generated Notes</h2>
              <button
                onClick={() => setNotesResult(null)}
                className={`text-sm px-2 py-1 rounded ${isDark ? 'text-neutral-400 hover:bg-neutral-700' : 'text-slate-500 hover:bg-slate-100'}`}
              >
                ✕
              </button>
            </div>
            <div className={`flex-1 overflow-y-auto p-4 text-sm whitespace-pre-wrap ${isDark ? 'text-neutral-200' : 'text-slate-800'}`}>
              {notesResult}
            </div>
            <div className={`flex gap-2 p-3 border-t ${isDark ? 'border-neutral-700' : 'border-slate-200'}`}>
              <button
                onClick={copyNotes}
                className={`text-sm px-3 py-1.5 rounded-lg text-white transition ${isDark ? 'bg-neutral-600 hover:bg-neutral-500' : 'bg-slate-700 hover:bg-slate-800'}`}
              >
                Copy
              </button>
              <button
                onClick={downloadNotes}
                className="text-sm px-3 py-1.5 rounded-lg text-white bg-blue-600 hover:bg-blue-700 transition"
              >
                Download .md
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Flashcards modal */}
      {cardsResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-2xl max-h-[85vh] rounded-2xl shadow-xl border flex flex-col overflow-hidden ${
            isDark ? 'bg-neutral-800 border-neutral-700' : 'bg-white border-slate-200'
          }`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-neutral-700' : 'border-slate-200'}`}>
              <h2 className={`text-sm font-semibold ${isDark ? 'text-neutral-200' : 'text-slate-800'}`}>
                {cardsResult.cards.length} Flashcard{cardsResult.cards.length === 1 ? '' : 's'}
              </h2>
              <button
                onClick={() => { setCardsResult(null); setPushMessage(null) }}
                className={`text-sm px-2 py-1 rounded ${isDark ? 'text-neutral-400 hover:bg-neutral-700' : 'text-slate-500 hover:bg-slate-100'}`}
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2">
              {cardsResult.cards.map((card, i) => (
                <div
                  key={i}
                  className={`rounded-lg border p-3 text-sm flex gap-3 ${
                    isDark ? 'border-neutral-700 bg-neutral-900/40' : 'border-slate-200 bg-slate-50'
                  }`}
                >
                  <div className="flex-1">
                    <p className={`font-medium ${isDark ? 'text-neutral-100' : 'text-slate-900'}`}>{card.front}</p>
                    <p className={`mt-1 ${isDark ? 'text-neutral-400' : 'text-slate-600'}`}>{card.back}</p>
                  </div>
                  <button
                    onClick={() => removeCard(i)}
                    title="Remove card"
                    className={`shrink-0 text-xs px-2 py-1 rounded self-start ${
                      isDark ? 'text-neutral-500 hover:bg-neutral-700 hover:text-red-400' : 'text-slate-400 hover:bg-slate-200 hover:text-red-500'
                    }`}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>

            <div className={`flex flex-col gap-2 p-3 border-t ${isDark ? 'border-neutral-700' : 'border-slate-200'}`}>
              <div className="flex items-center gap-2">
                <label className={`text-xs shrink-0 ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>Deck</label>
                <input
                  value={deckName}
                  onChange={(e) => setDeckName(e.target.value)}
                  className={`flex-1 border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors ${
                    isDark ? 'bg-neutral-700 border-neutral-600 text-neutral-100' : 'bg-white border-slate-300 text-slate-900'
                  }`}
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handlePushToAnki}
                  disabled={cardsResult.cards.length === 0 || !deckName.trim()}
                  className={`text-sm px-3 py-1.5 rounded-lg text-white transition ${
                    isDark
                      ? 'bg-amber-600 hover:bg-amber-700 disabled:bg-neutral-700 disabled:text-neutral-500'
                      : 'bg-amber-600 hover:bg-amber-700 disabled:bg-slate-200 disabled:text-slate-400'
                  }`}
                >
                  Push to Anki
                </button>
                <button
                  onClick={downloadFlashcards}
                  disabled={cardsResult.cards.length === 0}
                  className={`text-sm px-3 py-1.5 rounded-lg text-white transition ${
                    isDark ? 'bg-neutral-600 hover:bg-neutral-500' : 'bg-slate-700 hover:bg-slate-800'
                  }`}
                >
                  Download .txt
                </button>
              </div>
              {pushMessage && (
                <p className={`text-xs ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>{pushMessage}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App