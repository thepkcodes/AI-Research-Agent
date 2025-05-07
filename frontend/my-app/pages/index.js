import { useState } from "react";
import Head from "next/head";

export default function Home() {
  const [query, setQuery] = useState("");
  const [numResults, setNumResults] = useState(5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResults(null);

    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: query, num_results: numResults }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.message || `Status ${res.status}`);
      }

      const data = await res.json();
      setResults(data);
    } catch (err) {
      console.error("API Error:", err);
      setError(
        err.message.includes("Failed to fetch")
          ? "Could not connect. Is the backend running?"
          : err.message
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <Head>
        <title>Research Agent</title>
        <meta name="description" content="AI-powered research assistant" />
      </Head>

      <h1 className="text-3xl font-bold mb-6 text-center">Research Agent</h1>

      <form onSubmit={handleSubmit} className="max-w-md mx-auto">
        <label className="block mb-2">Research Query:</label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your question"
          className="w-full px-3 py-2 border rounded mb-4"
          required
        />

        <label className="block mb-2">Number of results:</label>
        <input
          type="number"
          min="1"
          max="10"
          value={numResults}
          onChange={(e) => setNumResults(Number(e.target.value))}
          className="w-full px-3 py-2 border rounded mb-4"
        />

        <button
          type="submit"
          disabled={loading}
          className={`w-full py-2 rounded text-white ${
            loading ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error && (
        <div className="mt-4 p-3 bg-red-100 text-red-700 rounded">
          Error: {error}
        </div>
      )}

      {results && (
        <div className="mt-8">
          <h2 className="text-2xl font-bold mb-2">Summary</h2>
          <div className="whitespace-pre-line bg-gray-100 p-4 rounded">
            {results.summary}
          </div>

          <h2 className="text-2xl font-bold mt-6 mb-2">Sources</h2>
          <ul className="space-y-4">
            {results.results.map((r, i) => (
              <li key={i} className="border p-4 rounded hover:bg-gray-50">
                <h3 className="font-semibold">{r.title}</h3>
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 break-all"
                >
                  {r.url}
                </a>
                <p className="mt-1 text-gray-600">{r.snippet}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}