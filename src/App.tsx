import { useState, useEffect, useCallback, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { open } from '@tauri-apps/plugin-dialog';
import {
  Music, Save, Image as ImageIcon, UploadCloud,
  X, Camera, Trash2, CheckCircle, AlertCircle,
  Moon, Sun, Layers, FolderOpen
} from 'lucide-react';
import './App.css';

interface AudioFile {
  path: string;
  filename: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  year: number | null;
  genre: string | null;
  track: number | null;
  has_art: boolean;
}

interface BatchFields {
  album: string;
  artist: string;
  year: string;
  genre: string;
}

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error';
}

let toastCounter = 0;

function App() {
  const [files, setFiles]             = useState<AudioFile[]>([]);
  const [activeFile, setActiveFile]   = useState<AudioFile | null>(null);
  const [albumArt, setAlbumArt]       = useState<string | null>(null);
  const [isSaving, setIsSaving]       = useState(false);
  const [isSavingAll, setIsSavingAll] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [toasts, setToasts]           = useState<Toast[]>([]);
  const [darkMode, setDarkMode]       = useState(() => localStorage.getItem('craftag-theme') === 'dark');

  // Multi-select
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [lastClickedPath, setLastClickedPath] = useState<string | null>(null);

  // Batch editor
  const [batchFields, setBatchFields] = useState<BatchFields>({ album: '', artist: '', year: '', genre: '' });
  const [batchArt, setBatchArt]       = useState<string | null>(null);
  const [batchArtPath, setBatchArtPath] = useState<string | null>(null);
  const [isApplying, setIsApplying]   = useState(false);

  const handleSaveRef = useRef<() => void>(() => {});

  // Derived
  const selectedFiles = files.filter(f => selectedPaths.has(f.path));
  const isBatchMode   = selectedFiles.length >= 2;

  /* ── Toast ──────────────────────────────────────────── */
  const addToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = ++toastCounter;
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3000);
  }, []);

  /* ── Theme ──────────────────────────────────────────── */
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
    localStorage.setItem('craftag-theme', darkMode ? 'dark' : 'light');
    
    // Show window once React is ready to eliminate startup flash
    setTimeout(() => {
      getCurrentWindow().show();
    }, 50);
  }, [darkMode]);

  /* ── Load queue on mount ────────────────────────────── */
  useEffect(() => {
    const saved = localStorage.getItem('craftag-queue');
    if (saved) {
      try {
        const paths = JSON.parse(saved);
        if (Array.isArray(paths) && paths.length > 0) {
          invoke<AudioFile[]>('read_audio_tags', { paths }).then(parsed => {
            setFiles(parsed);
          }).catch(err => console.error("Failed to restore queue", err));
        }
      } catch (e) {
        console.error("Failed to parse saved queue", e);
      }
    }
  }, []);

  /* ── Save queue on change ───────────────────────────── */
  useEffect(() => {
    const paths = files.map(f => f.path);
    localStorage.setItem('craftag-queue', JSON.stringify(paths));
  }, [files]);

  /* ── Pre-populate batch fields when selection changes ── */
  useEffect(() => {
    const sel = files.filter(f => selectedPaths.has(f.path));
    if (sel.length < 2) return;
    const common = (get: (f: AudioFile) => string | null | undefined) => {
      const vals = sel.map(get);
      return vals.every(v => v === vals[0]) ? (vals[0] ?? '') : '';
    };
    setBatchFields({
      album:  common(f => f.album),
      artist: common(f => f.artist),
      year:   common(f => f.year?.toString()),
      genre:  common(f => f.genre),
    });
    setBatchArt(null);
    setBatchArtPath(null);
  }, [selectedPaths]); // eslint-disable-line

  /* ── Tauri events + keyboard ────────────────────────── */
  useEffect(() => {
    const unlistenDrop = listen<{ paths: string[] }>('tauri://drag-drop', async (event) => {
      setIsDraggingOver(false);
      try {
        const paths = event.payload.paths;
        if (!paths?.length) return;
        const parsed: AudioFile[] = await invoke('read_audio_tags', { paths });
        setFiles(prev => {
          const existing = new Set(prev.map(f => f.path));
          return [...prev, ...parsed.filter(f => !existing.has(f.path))];
        });
      } catch { addToast('Failed to read dropped files.', 'error'); }
    });
    const unlistenOver  = listen('tauri://drag-over',  () => setIsDraggingOver(true));
    const unlistenLeave = listen('tauri://drag-leave', () => setIsDraggingOver(false));

    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        handleSaveRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      unlistenDrop.then(u => u());
      unlistenOver.then(u => u());
      unlistenLeave.then(u => u());
      window.removeEventListener('keydown', onKey);
    };
  }, [addToast]);

  /* ── Open files via native picker ───────────────────── */
  const handleOpenFiles = useCallback(async () => {
    try {
      const selected = await open({
        multiple: true,
        filters: [{ name: 'Audio', extensions: ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus'] }],
      });
      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      const parsed: AudioFile[] = await invoke('read_audio_tags', { paths });
      setFiles(prev => {
        const existing = new Set(prev.map(f => f.path));
        return [...prev, ...parsed.filter(f => !existing.has(f.path))];
      });
    } catch { addToast('Failed to open files.', 'error'); }
  }, [addToast]);

  /* ── Open folder via native picker ──────────────────── */
  const handleOpenFolder = useCallback(async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (!selected || typeof selected !== 'string') return;
      // read_audio_tags supports directories via WalkDir in Rust
      const parsed: AudioFile[] = await invoke('read_audio_tags', { paths: [selected] });
      setFiles(prev => {
        const existing = new Set(prev.map(f => f.path));
        return [...prev, ...parsed.filter(f => !existing.has(f.path))];
      });
    } catch { addToast('Failed to open folder.', 'error'); }
  }, [addToast]);

  /* ── Single-file select ─────────────────────────────── */
  const handleSelectFile = async (file: AudioFile) => {
    setActiveFile(file);
    setAlbumArt(null);
    if (file.has_art) {
      try {
        const art = await invoke<string | null>('get_album_art', { path: file.path });
        setAlbumArt(art);
      } catch { /* silent */ }
    }
  };

  /* ── Multi-select click handler ─────────────────────── */
  const handleFileClick = (file: AudioFile, e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey) {
      setSelectedPaths(prev => {
        const next = new Set(prev);
        // On first cmd+click, pull the already-active file into the set
        if (next.size <= 1 && activeFile) next.add(activeFile.path);
        next.has(file.path) ? next.delete(file.path) : next.add(file.path);
        return next;
      });
      setLastClickedPath(file.path);
    } else if (e.shiftKey && lastClickedPath) {
      const li = files.findIndex(f => f.path === lastClickedPath);
      const ci = files.findIndex(f => f.path === file.path);
      const [s, e2] = li <= ci ? [li, ci] : [ci, li];
      const range = files.slice(s, e2 + 1).map(f => f.path);
      setSelectedPaths(prev => {
        const next = new Set([...prev, ...range]);
        if (activeFile) next.add(activeFile.path);
        return next;
      });
      setLastClickedPath(file.path);
    } else {
      // Normal click → single mode
      setSelectedPaths(new Set([file.path]));
      setLastClickedPath(file.path);
      handleSelectFile(file);
    }
  };

  const clearSelection = () => {
    if (activeFile) {
      setSelectedPaths(new Set([activeFile.path]));
    } else {
      setSelectedPaths(new Set());
    }
  };

  /* ── Single-file field change ───────────────────────── */
  const handleChange = (field: keyof AudioFile, value: any) => {
    if (!activeFile) return;
    const updated = { ...activeFile, [field]: value };
    setActiveFile(updated);
    setFiles(prev => prev.map(f => f.path === activeFile.path ? updated : f));
  };

  /* ── Save single file ───────────────────────────────── */
  const handleSave = useCallback(async () => {
    if (!activeFile || isSaving) return;
    setIsSaving(true);
    try {
      await invoke('save_audio_tags', { file: activeFile });
      addToast('Tags saved.', 'success');
    } catch { addToast('Failed to save tags.', 'error'); }
    finally { setIsSaving(false); }
  }, [activeFile, isSaving, addToast]);

  useEffect(() => { handleSaveRef.current = handleSave; }, [handleSave]);

  /* ── Save all ───────────────────────────────────────── */
  const handleSaveAll = async () => {
    if (!files.length || isSavingAll) return;
    setIsSavingAll(true);
    let ok = 0, fail = 0;
    for (const file of files) {
      try { await invoke('save_audio_tags', { file }); ok++; }
      catch { fail++; }
    }
    setIsSavingAll(false);
    fail === 0
      ? addToast(`All ${ok} files saved.`, 'success')
      : addToast(`${ok} saved, ${fail} failed.`, 'error');
  };

  /* ── Remove from queue ──────────────────────────────── */
  const handleRemoveFile = (path: string) => {
    setFiles(prev => prev.filter(f => f.path !== path));
    setSelectedPaths(prev => { const n = new Set(prev); n.delete(path); return n; });
    if (activeFile?.path === path) { setActiveFile(null); setAlbumArt(null); }
  };

  /* ── Clear queue ────────────────────────────────────── */
  const handleClearQueue = () => {
    setFiles([]);
    setSelectedPaths(new Set());
    setActiveFile(null);
    setAlbumArt(null);
    addToast('Queue cleared.', 'success');
  };

  /* ── Single-file art ────────────────────────────────── */
  const handleArtUpload = async () => {
    if (!activeFile) return;
    try {
      const selected = await open({ multiple: false, filters: [{ name: 'Images', extensions: ['jpg','jpeg','png','gif','bmp'] }] });
      if (!selected || typeof selected !== 'string') return;
      await invoke('set_album_art', { audioPath: activeFile.path, imagePath: selected });
      const art = await invoke<string | null>('get_album_art', { path: activeFile.path });
      setAlbumArt(art);
      const updated = { ...activeFile, has_art: true };
      setActiveFile(updated);
      setFiles(prev => prev.map(f => f.path === activeFile.path ? updated : f));
      addToast('Album art updated.', 'success');
    } catch { addToast('Failed to set album art.', 'error'); }
  };

  const handleRemoveArt = async () => {
    if (!activeFile) return;
    try {
      await invoke('remove_album_art', { audioPath: activeFile.path });
      setAlbumArt(null);
      const updated = { ...activeFile, has_art: false };
      setActiveFile(updated);
      setFiles(prev => prev.map(f => f.path === activeFile.path ? updated : f));
      addToast('Album art removed.', 'success');
    } catch { addToast('Failed to remove album art.', 'error'); }
  };

  /* ── Batch art ──────────────────────────────────────── */
  const handleBatchArtUpload = async () => {
    try {
      const selected = await open({ multiple: false, filters: [{ name: 'Images', extensions: ['jpg','jpeg','png','gif','bmp'] }] });
      if (!selected || typeof selected !== 'string') return;
      setBatchArtPath(selected);
      const preview = await invoke<string>('read_image', { path: selected });
      setBatchArt(preview);
    } catch { addToast('Failed to load image.', 'error'); }
  };

  /* ── Apply batch ────────────────────────────────────── */
  const handleApplyBatch = async () => {
    if (!selectedFiles.length || isApplying) return;
    setIsApplying(true);
    let ok = 0, fail = 0;
    for (const file of selectedFiles) {
      try {
        const updated: AudioFile = {
          ...file,
          album:  batchFields.album  || file.album,
          artist: batchFields.artist || file.artist,
          year:   batchFields.year   ? parseInt(batchFields.year) : file.year,
          genre:  batchFields.genre  || file.genre,
        };
        await invoke('save_audio_tags', { file: updated });
        if (batchArtPath) {
          await invoke('set_album_art', { audioPath: file.path, imagePath: batchArtPath });
          updated.has_art = true;
        }
        setFiles(prev => prev.map(f => f.path === file.path ? updated : f));
        // Keep activeFile in sync if it was in the batch
        if (activeFile?.path === file.path) setActiveFile(updated);
        ok++;
      } catch { fail++; }
    }
    setIsApplying(false);
    fail === 0
      ? addToast(`Applied to ${ok} file${ok > 1 ? 's' : ''}.`, 'success')
      : addToast(`${ok} succeeded, ${fail} failed.`, 'error');
  };

  /* ── Render ─────────────────────────────────────────── */
  return (
    <div className="app-root">
      {/* Titlebar */}
      <div className="titlebar" data-tauri-drag-region>
        <span className="titlebar-title">Craftag</span>
        <button
          className="theme-toggle"
          style={{ marginLeft: 'auto' }}
          onClick={() => setDarkMode(d => !d)}
          title={darkMode ? 'Light mode' : 'Dark mode'}
          id="btn-theme-toggle"
        >
          {darkMode ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>

      <div className="main-container">
        {/* ── Sidebar ── */}
        <div className="sidebar">
          <div className="sidebar-header">
            <h2>Queue ({files.length})</h2>
            <div className="sidebar-actions">
              <button className="icon-btn" onClick={handleOpenFiles} title="Open files" id="btn-open-files">
                <UploadCloud size={15} />
              </button>
              <button className="icon-btn" onClick={handleOpenFolder} title="Open folder" id="btn-open-folder">
                <FolderOpen size={15} />
              </button>
              {files.length > 0 && (
                <>
                  <button className="icon-btn" onClick={handleClearQueue} title="Clear queue" id="btn-clear-queue">
                    <Trash2 size={15} />
                  </button>
                  <button className="save-all-btn" onClick={handleSaveAll} disabled={isSavingAll} id="btn-save-all">
                    {isSavingAll ? 'Saving…' : 'Save All'}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Multi-select banner */}
          {isBatchMode && (
            <div className="batch-banner">
              <Layers size={13} />
              <span>{selectedFiles.length} selected</span>
              <button className="clear-selection-btn" onClick={clearSelection}>Clear</button>
            </div>
          )}

          <div className="file-list">
            {files.map(file => {
              const isSelected = selectedPaths.has(file.path);
              const isActive   = activeFile?.path === file.path && !isBatchMode;
              return (
                <div
                  key={file.path}
                  className={`file-item ${isActive ? 'active' : ''} ${isBatchMode && isSelected ? 'selected' : ''}`}
                  onClick={e => handleFileClick(file, e)}
                >
                  {isBatchMode && (
                    <div className={`check-dot ${isSelected ? 'checked' : ''}`} />
                  )}
                  <Music size={16} className="file-icon" />
                  <div className="file-info" title={`${file.title || file.filename}\n${file.artist || 'Unknown Artist'}`}>
                    <div className="file-title">{file.title || file.filename}</div>
                    <div className="file-artist">{file.artist || 'Unknown Artist'}</div>
                  </div>
                  <button
                    className="remove-btn"
                    onClick={e => { e.stopPropagation(); handleRemoveFile(file.path); }}
                    title="Remove"
                  >
                    <X size={13} />
                  </button>
                </div>
              );
            })}
            {files.length === 0 && <p className="sidebar-empty">No files yet</p>}
          </div>
        </div>

        {/* ── Editor ── */}
        <div className="editor-area">
          {isBatchMode ? (
            /* BATCH EDITOR */
            <div className="editor-container">
              <div className="batch-header">
                <Layers size={20} className="batch-icon" />
                <div>
                  <h2>{selectedFiles.length} Files Selected</h2>
                  <p className="batch-subtitle">
                    Set shared tags · empty fields will not be changed
                  </p>
                </div>
              </div>

              <div className="editor-top-row">
                <div className="art-section">
                  <div className="art-preview" onClick={handleBatchArtUpload} title="Set album art for all files">
                    {batchArt
                      ? <img src={batchArt} alt="Batch Art" />
                      : <div className="art-placeholder"><ImageIcon size={28} /><span>Set Art</span></div>
                    }
                    <div className="art-overlay"><Camera size={18} /><span>Choose</span></div>
                  </div>
                  {batchArt && (
                    <button className="remove-art-btn" onClick={() => { setBatchArt(null); setBatchArtPath(null); }}>
                      <Trash2 size={13} /> Remove
                    </button>
                  )}
                </div>

                <div className="batch-file-list-preview">
                  {selectedFiles.slice(0, 6).map(f => (
                    <div key={f.path} className="batch-file-chip" title={f.title || f.filename}>
                      <Music size={11} />
                      <span>{f.title || f.filename}</span>
                    </div>
                  ))}
                  {selectedFiles.length > 6 && (
                    <div className="batch-file-chip muted">+{selectedFiles.length - 6} more</div>
                  )}
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group full-width">
                  <label>Album</label>
                  <input
                    type="text"
                    value={batchFields.album}
                    onChange={e => setBatchFields(p => ({ ...p, album: e.target.value }))}
                    placeholder="Album name for all files"
                  />
                </div>
                <div className="form-group">
                  <label>Artist</label>
                  <input
                    type="text"
                    value={batchFields.artist}
                    onChange={e => setBatchFields(p => ({ ...p, artist: e.target.value }))}
                    placeholder="Artist for all files"
                  />
                </div>
                <div className="form-group">
                  <label>Genre</label>
                  <input
                    type="text"
                    value={batchFields.genre}
                    onChange={e => setBatchFields(p => ({ ...p, genre: e.target.value }))}
                    placeholder="Genre for all files"
                  />
                </div>
                <div className="form-group">
                  <label>Year</label>
                  <input
                    type="number"
                    value={batchFields.year}
                    onChange={e => setBatchFields(p => ({ ...p, year: e.target.value }))}
                    placeholder="YYYY"
                  />
                </div>
              </div>

              <div className="actions">
                <button className="secondary" onClick={clearSelection}>Cancel</button>
                <button className="primary" onClick={handleApplyBatch} disabled={isApplying} id="btn-apply-batch">
                  {isApplying ? 'Applying…' : `Apply to ${selectedFiles.length} files`}
                </button>
              </div>
            </div>
          ) : activeFile ? (
            /* SINGLE FILE EDITOR */
            <div className="editor-container">
              <div className="editor-top-row">
                <div className="art-section">
                  <div className="art-preview" onClick={handleArtUpload} title="Click to change album art">
                    {albumArt
                      ? <img src={albumArt} alt="Album Art" />
                      : <div className="art-placeholder"><ImageIcon size={28} /><span>No Art</span></div>
                    }
                    <div className="art-overlay"><Camera size={18} /><span>Change</span></div>
                  </div>
                  {albumArt && (
                    <button className="remove-art-btn" onClick={handleRemoveArt}>
                      <Trash2 size={13} /> Remove
                    </button>
                  )}
                </div>
                <div className="track-header">
                  <h2>{activeFile.title || activeFile.filename}</h2>
                  <p className="track-path">{activeFile.path}</p>
                </div>
              </div>

              <div className="form-grid">
                <div className="form-group full-width">
                  <label htmlFor="field-title">Title</label>
                  <input id="field-title" type="text" value={activeFile.title || ''}
                    onChange={e => handleChange('title', e.target.value)} placeholder="Track Title" />
                </div>
                <div className="form-group">
                  <label htmlFor="field-artist">Artist</label>
                  <input id="field-artist" type="text" value={activeFile.artist || ''}
                    onChange={e => handleChange('artist', e.target.value)} placeholder="Artist Name" />
                </div>
                <div className="form-group">
                  <label htmlFor="field-album">Album</label>
                  <input id="field-album" type="text" value={activeFile.album || ''}
                    onChange={e => handleChange('album', e.target.value)} placeholder="Album Name" />
                </div>
                <div className="form-group">
                  <label htmlFor="field-year">Year</label>
                  <input id="field-year" type="number" value={activeFile.year || ''}
                    onChange={e => handleChange('year', e.target.value ? parseInt(e.target.value) : null)} placeholder="YYYY" />
                </div>
                <div className="form-group">
                  <label htmlFor="field-genre">Genre</label>
                  <input id="field-genre" type="text" value={activeFile.genre || ''}
                    onChange={e => handleChange('genre', e.target.value)} placeholder="e.g. Electronic" />
                </div>
                <div className="form-group">
                  <label htmlFor="field-track">Track No</label>
                  <input id="field-track" type="number" value={activeFile.track || ''}
                    onChange={e => handleChange('track', e.target.value ? parseInt(e.target.value) : null)} placeholder="e.g. 1" />
                </div>
              </div>

              <div className="actions">
                <button className="primary" id="btn-save" onClick={handleSave} disabled={isSaving}>
                  {isSaving ? 'Saving…' : 'Save Tags'}
                </button>
              </div>
            </div>
          ) : (
            /* EMPTY / DROP STATE */
            <div className="empty-state">
              <div
                className={`dropzone ${isDraggingOver ? 'dragging' : ''}`}
                onClick={handleOpenFiles}
                role="button" tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && handleOpenFiles()}
                aria-label="Open or drop audio files"
              >
                <UploadCloud size={44} className="dropzone-icon" />
                <h3>Drop Files/Folders or Click to Open Files</h3>
                <p>MP3, WAV, FLAC, AAC and more</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Toasts */}
      <div className="toast-container" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {t.type === 'success' ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
