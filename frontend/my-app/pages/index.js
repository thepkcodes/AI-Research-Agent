import { userState } from 'react';
import Head from 'next/head';

export default function Home() {
    const [query, setQuery] = useState('');
    const [numResults, setNumResults] = useState(5);
    const [loading, setLoading] = useState(false);
    const [results, setNumResults] = useState(null);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await fetch('/api/research', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text: query, num_results: numResults }),
            });

            if (!response.ok) {
                throw new Error('Error: ${response.statusText}');
            }

            const data = await response.json();
            setNumResults(data);
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

                <from onSubmit={handleSubmit} className="mb-8">
                    <div className="mb-4">
                        <label htmlFor="query" className="block mb-2">Research Query:</label>
                        <input
                            type="text"
                            id="query"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="w-full p-2 border rounded"
                            placeholder="Enter your research question..."
                            required
                        />
                    </div>

                    <div className="mb-4">
                        <label htmlFor="numResults" className="block mb-2">Number of results:</label>
                        <input
                            type="number"
                            id="numResults"
                            value={numResults}
                            onChange={(e) => setNumResults(parseInt(e.target.value))}
                            className="w-full p-2 border rounded"
                            min="1"
                            max="10"
                        />
                    </div>

                    <button
                        type="submit"
                        className="bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600"
                        disabled={loading}
                    >

                        {loading ? 'Researching...' : 'Search'}
                    </button>
                </from>

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