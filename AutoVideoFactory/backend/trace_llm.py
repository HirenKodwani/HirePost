import httpx, sys, os, asyncio

original_post = httpx.AsyncClient.post
async def debug_post(self, url, *args, **kwargs):
    if 'ollama' in str(url) or '11434' in str(url):
        json_data = kwargs.get('json', {})
        has_images = 'images' in json_data and json_data['images']
        print(f"LLM CALL: url={url} model={json_data.get('model')} has_images={has_images}", flush=True)
        if has_images:
            print(f"*** IMAGES FOUND! *** images={json_data['images']}", flush=True)
            print(f"prompt={json_data.get('prompt','')[:200]}", flush=True)
        else:
            print(f"prompt={json_data.get('prompt','')[:80]}", flush=True)
    return await original_post(self, url, *args, **kwargs)

httpx.AsyncClient.post = debug_post

os.environ['AVF_LLM_PROVIDER'] = 'openai'
os.environ['AVF_LLM_MODEL'] = 'llama3.2:3b'
os.environ['AVF_OLLAMA_DEFAULT_MODEL'] = 'llama3.2:3b'
os.environ['AVF_LLM_MAX_TOKENS'] = '100'

from app.services.pipeline_orchestrator import ContentPipeline

async def test():
    pipe = ContentPipeline()
    pid = await pipe.run_full_pipeline({
        'topic': 'test topic',
        'niche': 'test',
        'duration': 10,
        'style': 'comedy',
        'publish': False,
    })
    result = pipe.get_pipeline(pid)
    print(f"Status: {result.get('status')}", flush=True)
    if result.get('error'):
        print(f"Error: {result['error']}", flush=True)

asyncio.run(test())
