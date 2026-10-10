// A failed connection is not evidence that the saved session has expired.
export async function checkSavedSession({ readToken, fetchUser, clear }) {
  const token = readToken()
  if (!token) return { status: 'anonymous', user: null }
  try {
    const user = await fetchUser()
    if (readToken() !== token) return { status: 'changed', user: null }
    return { status: 'authenticated', user }
  } catch (error) {
    // A response for an older token must not clear a newer login from another tab.
    if (readToken() !== token) return { status: 'changed', user: null }
    if (error.status === 401) {
      clear()
      return { status: 'anonymous', user: null }
    }
    return { status: 'unavailable', user: null, error }
  }
}
