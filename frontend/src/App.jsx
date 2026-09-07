import { useEffect, useState } from 'react'
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

  function toggleDoc(id) {
    setSelectedDocIds(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    )
  }

  function displayName(filename) {
    const parts = filename.split('_')
    return parts.length > 1 ? parts.slice(1).join('_') : filename
  }

  function handleSend() {
    if (isStreaming) return
    setIsStreaming(true)
    const userMessage = { role: 'user', content: inputValue }
    const assistantMessage = { role: 'assistant', content: '', citations: [] }

    setMessages(prev => [...prev, userMessage, assistantMessage])
    setInputValue('')

    streamChat(
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
        setIsStreaming(false)
      }
    )
  }

  async function handleUpload() {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('subject_id', selectedSubject)

    const response = await fetch('http://127.0.0.1:8000/upload', {
      method: 'POST',
      body: formData,
    })
    const data = await response.json()
    console.log(data)
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
          onSubmit={(e) => { e.preventDefault(); handleUpload(); }}
          className="flex flex-col gap-2"
        >
          <label className={`text-sm font-medium ${isDark ? 'text-neutral-300' : 'text-slate-600'}`}>
            Upload
          </label>
          <input
            type="file"
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
        </form>

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
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/30 text-xs opacity-80">
                    Sources: {msg.citations}
                  </div>
                )}
              </div>
            </div>
          ))}
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
    </div>
  )
}

export default App