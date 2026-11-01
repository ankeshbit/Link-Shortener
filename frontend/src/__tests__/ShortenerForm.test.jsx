import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ShortenerForm from '../components/ShortenerForm';
import api from '../api/axios';
import { BrowserRouter } from 'react-router-dom';

// Mock AuthContext
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { email: 'test@bytelink.co' },
  }),
}));

// Mock api
vi.mock('../api/axios', () => {
  const mockApi = {
    post: vi.fn(),
  };
  return {
    default: mockApi,
    API_BASE_URL: 'http://localhost:8000',
  };
});

describe('ShortenerForm Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submitting bare domain google.com calls the API with https://google.com', async () => {
    api.post.mockResolvedValueOnce({
      data: {
        short_url: 'http://localhost:8000/xyz123',
        short_id: 'xyz123',
        target_url: 'https://google.com',
      },
    });

    render(
      <BrowserRouter>
        <ShortenerForm />
      </BrowserRouter>
    );

    const input = screen.getByLabelText(/Long URL to shorten/i);
    fireEvent.change(input, { target: { value: 'google.com' } });

    const submitBtn = screen.getByRole('button', { name: /generate short link/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1);
    });

    expect(api.post).toHaveBeenCalledWith('/api/shorten', {
      target_url: 'https://google.com',
    });
  });

  it('displays exact server error message when API responds with {"status":"error","message":"Alias already in use"}', async () => {
    api.post.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          status: 'error',
          message: 'Alias already in use',
        },
      },
    });

    render(
      <BrowserRouter>
        <ShortenerForm />
      </BrowserRouter>
    );

    const input = screen.getByLabelText(/Long URL to shorten/i);
    fireEvent.change(input, { target: { value: 'https://example.com' } });

    const submitBtn = screen.getByRole('button', { name: /generate short link/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Alias already in use')).toBeInTheDocument();
    });
  });

  it('generates a 512px canvas when QR code download is triggered', async () => {
    api.post.mockResolvedValueOnce({
      data: {
        short_url: 'http://localhost:8000/qr123',
        short_id: 'qr123',
        target_url: 'https://example.com',
      },
    });

    const appendChildSpy = vi.spyOn(document.body, 'appendChild');

    render(
      <BrowserRouter>
        <ShortenerForm />
      </BrowserRouter>
    );

    const input = screen.getByLabelText(/Long URL to shorten/i);
    fireEvent.change(input, { target: { value: 'https://example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /generate short link/i }));

    await waitFor(() => {
      expect(screen.getByText('Download QR')).toBeInTheDocument();
    });

    // Mock createElement to capture the offscreen canvas
    let createdCanvas = null;
    const origCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
      const el = origCreateElement(tagName);
      if (tagName === 'canvas') {
        createdCanvas = el;
      }
      return el;
    });

    const downloadBtn = screen.getByText('Download QR');
    fireEvent.click(downloadBtn);

    expect(createdCanvas).not.toBeNull();
    expect(createdCanvas.width).toBe(512);
    expect(createdCanvas.height).toBe(512);

    appendChildSpy.mockRestore();
    document.createElement.mockRestore();
  });
});
