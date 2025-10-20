import { ref, nextTick } from 'vue';
import type { Ref } from 'vue';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { ElLoading, ElMessage } from 'element-plus';

type PreExportHook = () => Promise<void> | void;

export function useExport(elementRef: Ref<HTMLElement | null>, filename: string) {
  const isExporting = ref(false);

  const exportToPdf = async (preExportHook?: PreExportHook) => {
    if (!elementRef.value) {
      ElMessage.error('无法找到要导出的内容');
      return;
    }

    isExporting.value = true;
    const loadingInstance = ElLoading.service({
      lock: true,
      text: '正在准备导出内容...',
      background: 'rgba(0, 0, 0, 0.7)',
    });

    try {
      if (preExportHook) {
        await preExportHook();
      }
      
      await nextTick();
      await new Promise(resolve => setTimeout(resolve, 1000)); // 等待图表渲染

      loadingInstance.text.value = '正在逐页生成 PDF...';
      if (!elementRef.value) {
        throw new Error("导出目标元素已不存在。");
      }

      const pdf = new jsPDF('p', 'mm', 'a4');
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const margin = 10;
      const contentWidth = pdfWidth - margin * 2;
      let currentY = margin;

      // [核心重构] 找到所有独立的卡片作为分页单元
      const elementsToPrint = elementRef.value.querySelectorAll<HTMLElement>('.page-break-inside-avoid');

      for (let i = 0; i < elementsToPrint.length; i++) {
        const element = elementsToPrint[i];
        
        const canvas = await html2canvas(element, {
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
          allowTaint: true,
        });

        const imgHeight = canvas.height * (contentWidth / canvas.width);
        
        // 如果当前页剩余空间不足以放下这个卡片，则换页
        if (currentY + imgHeight > (pdf.internal.pageSize.getHeight() - margin)) {
          pdf.addPage();
          currentY = margin;
        }

        pdf.addImage(canvas.toDataURL('image/jpeg', 0.95), 'JPEG', margin, currentY, contentWidth, imgHeight);
        currentY += imgHeight + 5; // 增加 5mm 的卡片间距
      }
      
      pdf.save(`${filename}.pdf`);

    } catch (error) {
      console.error("导出 PDF 失败:", error);
      ElMessage.error('导出 PDF 失败，请稍后重试。');
    } finally {
      isExporting.value = false;
      loadingInstance.close();
    }
  };

  return {
    isExporting,
    exportToPdf,
  };
}