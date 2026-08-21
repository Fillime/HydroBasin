export type StoredProject<TPayload = unknown> = {
  id: string
  name: string
  client?: string
  calculatedBy?: string
  reviewedBy?: string
  description?: string
  createdAt: string
  updatedAt: string
  payload: TPayload
}

const DB_NAME = 'hydrobasin-local'
const STORE_NAME = 'projects'
const DB_VERSION = 1
const ACTIVE_PROJECT_KEY = 'hydrobasin.activeProjectId'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('updatedAt', 'updatedAt')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('No fue posible abrir el almacenamiento local.'))
  })
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Error en el almacenamiento local.'))
  })
}

export async function listProjects<TPayload = unknown>(): Promise<StoredProject<TPayload>[]> {
  const db = await openDb()
  try {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const rows = await requestToPromise(store.getAll()) as StoredProject<TPayload>[]
    return rows.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  } finally {
    db.close()
  }
}

export async function getProject<TPayload = unknown>(id: string): Promise<StoredProject<TPayload> | null> {
  const db = await openDb()
  try {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    return (await requestToPromise(store.get(id)) as StoredProject<TPayload> | undefined) ?? null
  } finally {
    db.close()
  }
}

export async function putProject<TPayload>(project: StoredProject<TPayload>): Promise<void> {
  const db = await openDb()
  try {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    await requestToPromise(store.put(project))
  } finally {
    db.close()
  }
}

export async function deleteProject(id: string): Promise<void> {
  const db = await openDb()
  try {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    await requestToPromise(store.delete(id))
  } finally {
    db.close()
  }
}

export function createProjectId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `project-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function getActiveProjectId(): string {
  try {
    return localStorage.getItem(ACTIVE_PROJECT_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setActiveProjectId(id: string): void {
  try {
    if (id) localStorage.setItem(ACTIVE_PROJECT_KEY, id)
    else localStorage.removeItem(ACTIVE_PROJECT_KEY)
  } catch {
    // El proyecto sigue funcionando aunque el navegador bloquee localStorage.
  }
}
