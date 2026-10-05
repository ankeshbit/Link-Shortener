import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { onAuthStateChanged, signOut as firebaseSignOut } from 'firebase/auth';
import { auth, signInWithGoogle as firebaseGoogleSignIn } from './firebase';
import api from '../api/axios';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Centralized Firebase Auth state observer
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      if (currentUser) {
        try {
          const token = await currentUser.getIdToken();
          localStorage.setItem('token', token);
          setUser({
            uid: currentUser.uid,
            email: currentUser.email,
            displayName: currentUser.displayName,
            photoURL: currentUser.photoURL,
          });
        } catch (error) {
          console.error('Failed to retrieve Firebase ID token:', error);
          localStorage.removeItem('token');
          setUser(null);
        }
      } else {
        localStorage.removeItem('token');
        setUser(null);
      }
      setLoading(false);
      window.dispatchEvent(new Event('authchange'));
    });

    return () => unsubscribe();
  }, []);

  const loginWithGoogle = async () => {
    const { user: firebaseUser, idToken } = await firebaseGoogleSignIn();
    localStorage.setItem('token', idToken);
    
    // Explicit sync with FastAPI backend to ensure user record exists in Neon PostgreSQL
    try {
      await api.post('/api/auth/sync');
    } catch (err) {
      console.warn('Backend user sync warning:', err);
    }

    const userData = {
      uid: firebaseUser.uid,
      email: firebaseUser.email,
      displayName: firebaseUser.displayName,
      photoURL: firebaseUser.photoURL,
    };
    setUser(userData);
    window.dispatchEvent(new Event('authchange'));
    return userData;
  };

  const signOut = async () => {
    try {
      await firebaseSignOut(auth);
    } catch (err) {
      console.error('Error during sign out:', err);
    } finally {
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      setUser(null);
      window.dispatchEvent(new Event('authchange'));
    }
  };

  const getIdToken = async (forceRefresh = false) => {
    if (!auth.currentUser) return null;
    const token = await auth.currentUser.getIdToken(forceRefresh);
    localStorage.setItem('token', token);
    return token;
  };

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      loginWithGoogle,
      signOut,
      getIdToken,
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);
