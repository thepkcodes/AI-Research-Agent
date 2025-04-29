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
                    </div>
                </from>
            </main>
        </div>
    )
}