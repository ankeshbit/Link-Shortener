import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import Dashboard from '../components/Dashboard';
import api from '../api/axios';
import * as AuthContextModule from '../auth/AuthContext';
import { BrowserRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/axios', () => {
  const mockApi = {
    get: vi.fn(),
    delete: vi.fn(),
  };
  return {
    default: mockApi,
    API_BASE_URL: 'http://localhost:8000',
  };
});

describe('401 Redirect Loop Guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('simulates Firebase user present + /api/user/links returning 401 and asserts signOut called once, navigation to /login, and no further requests', async () => {
    const mockSignOut = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      user: { email: 'user@bytelink.co' },
      signOut: mockSignOut,
    });

    api.get.mockRejectedValue({
      response: {
        status: 401,
        data: { status: 'error', message: 'Token invalid or expired' },
      },
    });

    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalledTimes(1);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/login', {
      state: { sessionExpired: true },
    });

    // Verify exactly 1 request was made and no loop/further requests occurred
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});
