import { useEffect, useState } from 'react';
import { getModelInfo, getHistory } from '../services/api.js';

export function useModelInfo() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    getModelInfo().then(setData).catch((e) => setError(e.message));
  }, []);
  return { data, error };
}

export function useHistory() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    getHistory()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  return { data, error, loading };
}
