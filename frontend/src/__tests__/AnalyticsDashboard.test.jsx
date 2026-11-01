import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import AnalyticsDashboard from '../components/AnalyticsDashboard';
import api from '../api/axios';
import { BrowserRouter } from 'react-router-dom';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'mock-short-id' }),
  };
});

// Mock ChartJS to avoid canvas context errors in jsdom
vi.mock('react-chartjs-2', () => ({
  Bar: () => <div data-testid="mock-bar-chart" />,
}));

vi.mock('../api/axios', () => {
  const mockApi = {
    get: vi.fn(),
  };
  return {
    default: mockApi,
    API_BASE_URL: 'http://localhost:8000',
  };
});

describe('AnalyticsDashboard Resilience and Error States', () => {
  let wsInstances = [];

  beforeEach(() => {
    vi.clearAllMocks();
    wsInstances = [];

    // Mock WebSocket globally
    class MockWebSocket {
      constructor(url) {
        this.url = url;
        this.send = vi.fn();
        this.close = vi.fn();
        wsInstances.push(this);
      }
    }
    window.WebSocket = MockWebSocket;
  });

  it('keeps old stats visible with an alert banner on failed poll', async () => {
    const validStats = {
      target_url: 'https://example.com/target',
      total_clicks: 128,
      countries: { US: 50 },
      recent_clicks: [],
    };

    // First fetch succeeds
    api.get.mockResolvedValueOnce({ data: validStats });

    render(
      <BrowserRouter>
        <AnalyticsDashboard />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('128')).toBeInTheDocument();
    });

    // Subsequent poll fails with 500
    api.get.mockRejectedValueOnce({
      response: { status: 500, data: 'Internal Server Error' },
    });

    // Close WS to trigger polling fetch
    if (wsInstances[0]?.onclose) {
      act(() => {
        wsInstances[0].onclose();
      });
    }

    // Wait for the poll error banner
    await waitFor(() => {
      expect(
        screen.getByText(/Unable to refresh live stats\. Showing cached metrics\./i)
      ).toBeInTheDocument();
    });

    // Verify original stats are STILL visible!
    expect(screen.getByText('128')).toBeInTheDocument();
    expect(screen.getByText(/https:\/\/example\.com\/target/i)).toBeInTheDocument();
  });

  it('stops WebSocket retry and polling after HTTP 404', async () => {
    vi.useFakeTimers();

    api.get.mockRejectedValue({
      response: { status: 404, data: { status: 'error', message: 'Not found' } },
    });

    render(
      <BrowserRouter>
        <AnalyticsDashboard />
      </BrowserRouter>
    );

    await act(async () => {
      // Let initial fetch reject
      await Promise.resolve();
    });

    expect(screen.getByText(/This short link does not exist\./i)).toBeInTheDocument();

    const callCountAfter404 = api.get.mock.calls.length;

    // Advance timers by 30 seconds
    act(() => {
      vi.advanceTimersByTime(30000);
    });

    // Assert no further polling or retry calls were made
    expect(api.get.mock.calls.length).toBe(callCountAfter404);

    vi.useRealTimers();
  });
});
