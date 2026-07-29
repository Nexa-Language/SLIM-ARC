import os
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read results from a file')
    parser.add_argument('--result_dir', type=str, help='Directory containing the results')
    parser.add_argument('--result_type', type=str, help='Type of the results', default='prefill,decode')
    parser.add_argument('--output_path', type=str, help='Path to save the results', default=None)
    parser.add_argument('--methods', type=str, help='Methods to consider', default="mmap,syncio,prefetch")
    args = parser.parse_args()
    args.result_type = args.result_type.split(',')
    args.methods = args.methods.split(',')

    if not os.path.exists(args.result_dir):
        print('Directory does not exist')
        exit(1)

    results = {}
    mem_list = {}
    for file in os.listdir(args.result_dir):
        if not file.endswith('.txt'):
            continue
        with open(os.path.join(args.result_dir, file), 'r') as f:
            lines = f.readlines()

        file = file.split('/')[-1].split('.')[0]
        mem = file.split('-')[-1]
        method = file.split('-')[-2]
        model = '-'.join(file.split('-')[1:-2])
        if model not in results:
            results[model] = {}
        if method not in results[model]:
            results[model][method] = {}
        for t in args.result_type:
            if t not in results[model][method]:
                results[model][method][t] = {}
        mem_list[mem] = float(mem)
        prefill_throughput = -1
        decode_throughput = -1
        for line in lines:
            line = line.strip()
            if not line.startswith('llama_perf_context_print'):
                continue
            items = [item for item in line.split(' ') if item.replace('.', '', 1).isdigit()]
            if 'llama_perf_context_print: prompt eval time' in line:
                prefill_throughput = float(items[-1])
            if 'llama_perf_context_print:        eval time' in line:
                decode_throughput = float(items[-1])
        if 'prefill' in args.result_type:
            results[model][method]['prefill'][mem] = prefill_throughput
        if 'decode' in args.result_type:
            results[model][method]['decode'][mem] = decode_throughput

    if args.output_path is not None:
        mem_list = list(mem_list.items())
        mem_list.sort(key=lambda x: x[1])
        mem_list = [mem[0] for mem in mem_list]
        with open(args.output_path, 'w') as f:
            for model, methods in results.items():
                f.write(f'{model}\t')
                for mem in mem_list:
                    f.write(f'{mem}\t')
                f.write('\n')
                for method in args.methods:
                    metrics = methods[method]
                    f.write(f'{method}\t')
                    if 'prefill' in args.result_type:
                        for mem in mem_list:
                            f.write(f'{metrics["prefill"][mem]}\t')
                    if 'decode' in args.result_type:
                        for mem in mem_list:
                            f.write(f'{metrics["decode"][mem]}\t')
                    f.write('\n')