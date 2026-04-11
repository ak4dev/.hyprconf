import { SectionHeading, AccordionGroup, CodeBlock } from '@/components/ui';
import { CLI_GROUPS } from '@/content';
import styles from './CLI.module.css';

export default function CLI() {
  return (
    <div className={styles.page}>
      <SectionHeading id="cli-reference">CLI & TUI Reference</SectionHeading>
      <p className={styles.intro}>
        <code>hyprconf</code> is the command-line interface for managing your
        Hyprland environment. Run <code>hyprconf tui</code> for the interactive terminal UI,
        or use any subcommand directly from the shell.
      </p>

      <AccordionGroup>
        {CLI_GROUPS.map((group) => (
          <AccordionGroup.Item key={group.title} value={group.title.toLowerCase()}>
            <AccordionGroup.Trigger>{group.title}</AccordionGroup.Trigger>
            <AccordionGroup.Content>
              <div className={styles.commands}>
                {group.commands.map((cmd) => (
                  <div key={cmd.name} className={styles.command}>
                    <CodeBlock language="bash" prompt>
                      {cmd.usage}
                    </CodeBlock>
                    <p className={styles.cmdDesc}>{cmd.description}</p>
                    {cmd.example && (
                      <pre className={styles.exampleBlock}>{cmd.example}</pre>
                    )}
                  </div>
                ))}
              </div>
            </AccordionGroup.Content>
          </AccordionGroup.Item>
        ))}
      </AccordionGroup>
    </div>
  );
}
