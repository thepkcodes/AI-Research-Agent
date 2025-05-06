import { useState } from 'react';
import Head from 'next/head';

export default function Home() {
    const [query, setQuery] = useState('');
    const [numResults, setNumResults] = useState(5);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault(); // prevent page reload
      
        try {
          setLoading(true);
          setError('');
          const res = await fetch("http://127.0.0.1:8000/research", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: query, num_results: numResults })
          });          
      
          if (!res.ok) throw new Error('Failed to fetch');
      
          const data = await res.json();
          setResults(data);
        } catch (err) {
          setError(err.message);
        } finally {
          setLoading(false);
        }
      };
      

    return (
        <div className="container mx-auto px-4 py-8">
            <Head>
                <title>Research Agent</title>
                <meta name="description" content="AI=powered research assistant" />
            </Head>

            <main>
                <h1 className="text-3xl font-bold mb-6 text-center">Reseacrh Agent</h1>

                <form onSubmit={handleSubmit}>
                    <label>Research Query:</label>
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Enter your research question"
                    />
                    <br />
                    <label>Number of results:</label>
                    <input
                        type="number"
                        value={numResults}
                        onChange={(e) => setNumResults(Number(e.target.value))}
                    />
                    <br />
                    <button type="submit">Search</button>
                </form>
                {error && (
                    <div className="bg-red-100 borded-red-400 text-red-700 px-4 py-3 rounded mb-4">
                        {error}
                    </div>
                )}

                {results && (
                    <div className="results">
                        <h2 className="text-2xl font-bold mb-4">Summary</h2>
                        <div className="bg-gray-100 p-4 rounded mb-6 whitespace-pre-line">
                            {results.summary}
                        </div>

                        <h2 className="text-2xl font-bold mb-4">Sources</h2>
                        <ul className="space-y-4">
                            {results.results.map((result, index) => (
                                <li key={index} className="border p-4 rounded">
                                    <h3 className="font-bold">{result.title}</h3>
                                    <a href={result.url} className="text-blue-500 hover:underline" target="_blank" rel="noopener noreferrer">
                                        {result.url}
                                    </a>
                                    <p className="mt-2">{result.snippet}</p>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </main>
        </div>
    );
}