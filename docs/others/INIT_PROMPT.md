## 背景与材料

我们正在参与“全国大学生系统能力大赛-操作系统设计赛-挑战赛道”，选择了由主办方南开大学宫老师维护的赛题Proj 59 “内存受限环境的大语言模型推理优化问题”，具体赛题请参考 @/docs/official/赛题.txt 。我们需要完成这个赛题的代码构建和文档编写，目标是拿到尽可能好的数据从而进入决赛。

### 官方材料

在 @/docs/official 目录中，存放了比赛官方或者赛题维护的核心资料，是务必深入理解并严格遵循的底线规则。其中， @/docs/official/与宫老师邮件内容.txt 是我们询问宫老师的问题与他的回复，需要仔细阅读。而 @/docs/official/赛题.txt 则是最重要的题目遵循。

### 自主材料

在 @/docs/others 中是我们自己的内容，例如 @/docs/others/赛题与学习路径.pdf 是前期我们对于赛题的理解、学习路径，并在其中给出了一些初步思路，是应该重点关注的文件之一。而 @/docs/others/INIT_PROMPT.md 就是现在我正在发给你的这个prompt，里面有很多相关信息可以复习。 @/docs/others/logo 是我们的logo，其中 @/docs/others/logo/logo_nobg.png 是1:1的无背景版本，可以广泛使用。而llama.cpp目录则是标准的cpu运行时目录。

### 相关论文

在 @/docs/papers 中是我们找到的有关paper与其代码。其中最重要的是就是宫老师在赛题中直接提到的 @/docs/papers/FlexInfer\ Breaking\ Memory\ Constraint\ via\ Flexible\ and\ Efficient\ Offloading\ for\ On-Device\ LLM\ Inference.pdf 这篇论文，其开源代码库在 @/docs/papers/FlexInfer 中。而 @/docs/papers/On-Device\ Large\ Language\ Models\ A\ Survey\ of\ Model\ Compression\ and\ System\ Optimization.pdf 则是关于端侧模型的一篇最新综述，可以阅读它来深入了解当前发展，后续如果需要参考某项技术可以直接从里面找提到的相关最新论文或项目，然后上网找。
而 @/docs/papers/flexinfer-optimize.md 是我们调研中认为可以对flexinfer进行优化的方向。

### 当前目录

当前目录下有很多我建好的目录结构，但都是空的。建好是为了方便你后续按照这个结构直接开始写。你要先深入理解每个目录和文件的意义。

## 初始方向思路

根据赛题、宫老师邮件和我们前期学习的理解，对于llm端侧推理，一般有模型和系统两个维度大的工作，模型方面就是量化压缩剪枝蒸馏等技术，系统方面就是flexinfer这样对于操作系统/编译运行时/硬件等方面进行优化。我们最终选择就是，初赛阶段，在网上找开源的小模型，例如qwen3.5的0.8b到4b这种范围的模型（或者可以使用qwen3.5的稀疏moe，或者qwen3-next这种专门做超稀疏的），然后在系统优化这个方向上展开主要工作，基于现有的sota方法做融合或者进一步优化，也可以辅以量化压缩剪枝等，但这个不是我们的重点。

环境就放在当前你所在的wsl里面，用某种工具限制一个8GB-16GB的内存、适量cpu核的环境用于模拟受限环境，然后每次完成整个系统的优化后，从多个维度衡量当前端侧模型对比我们baseline+sota的运行结果，得出我们做了多少的优化。

目前我是准备先复现flexinfer的结果，跑它一遍作为sota，然后我们在它基础上做优化。优化方向非常多元，只要结果有优化即可。

## 你的初始任务

现在你先完整阅读所有需要的文件，然后谈谈你的理解，并问我一堆问题以明确边界。