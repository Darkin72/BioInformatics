import { useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { formatDateTime } from '../../shared/date'
import type { AdminUserList } from '../../shared/types'
import { deleteAdminUser, getAdminUsers, openAdminUsersEvents } from './adminApi'

export function AdminUsersPage() {
  const [remote, setRemote] = useState<AdminUserList | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [deletingUser, setDeletingUser] = useState<string | null>(null)
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'offline'>(
    'connecting',
  )
  const [error, setError] = useState<string | null>(null)

  async function loadUsers(showLoading = false) {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      setRemote(await getAdminUsers())
      setError(null)
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : 'Unable to load users.',
      )
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }

  async function handleDelete(username: string) {
    setDeletingUser(username)
    setError(null)
    try {
      setRemote(await deleteAdminUser(username))
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : 'Unable to delete user.',
      )
    } finally {
      setDeletingUser(null)
    }
  }

  useEffect(() => {
    void loadUsers(true)
  }, [])

  useEffect(() => {
    const close = openAdminUsersEvents(
      (users) => {
        setRemote(users)
        setError(null)
        setIsLoading(false)
        setStreamState('live')
      },
      () => setStreamState('offline'),
    )

    return close
  }, [])

  if (isLoading) {
    return <LoadingState />
  }

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>User management</h2>
          <p>
            {remote
              ? `${remote.returned} users | updated ${formatDateTime(remote.updated_at)} | stream ${streamState}`
              : 'Manage local application accounts.'}
          </p>
        </div>
      </div>

      {error ? <ErrorState message={error} /> : null}

      {!remote || remote.items.length === 0 ? (
        <EmptyState message="No users found." />
      ) : (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Type</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {remote.items.map((user) => (
                  <tr key={user.username}>
                    <td className="mono">{user.username}</td>
                    <td>{user.roles.join(', ')}</td>
                    <td>{user.is_admin ? 'Admin' : 'User'}</td>
                    <td>
                      {user.is_admin ? (
                        <span className="muted-copy">Configured in .env</span>
                      ) : (
                        <button
                          className="secondary-button"
                          disabled={deletingUser === user.username}
                          onClick={() => void handleDelete(user.username)}
                          type="button"
                        >
                          {deletingUser === user.username ? 'Deleting...' : 'Delete'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  )
}
